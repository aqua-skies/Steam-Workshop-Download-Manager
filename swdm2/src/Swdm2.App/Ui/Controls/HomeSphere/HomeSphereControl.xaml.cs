using System.Collections.ObjectModel;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Media3D;
using System.Windows.Threading;

namespace Swdm2.App.Ui.Controls.HomeSphere;

/// <summary>
/// 球体主页核心控件（D5.15;t2 v1.4 §2.8）：
/// - Viewport3D 二十面体细化球（subdivision=3 → 1280 三角面 ⚠️[待标定]）
/// - 相机=右下象限（位置 x+/y-/z+，看向球心）
/// - 缓顺时针自转（绕 Y 轴；⚠️[待标定] 起点 6°/s)
/// - 鼠标=PointLight 光源（accent 色；投影到球前方平面）
/// - 拖拽=轨道旋转（用户输入优先于自转）+惯性（摩擦 0.92/frame ⚠️[待标定]）
/// - 贴图三角面：方形 UV 贴边；悬停放大（顶点沿法向额外推 +0.012 ≈ 视觉 1.12)
/// - 对话泡泡=悬停时命中点上方游戏名；移开复原（Collapsed)
/// - 点击贴图=触发 GameTileClicked（宿主页跳 GameSelectPage)
/// 帧驱动=CompositionTarget.Rendering（UI 线程；60fps 目标，单帧预算 &lt;4ms 起点观测）。
/// </summary>
public partial class HomeSphereControl : UserControl
{
    // ⚠️[参数待重标定] 规格起点值（v1.4 §2.8.1/2.8.2/2.8.3)
    private const int Subdivision = 3;
    private const double AutoRotateRadiansPerSecond = 6.0 * Math.PI / 180.0;
    private const double OrbitFriction = 0.92;
    private const double OrbitSensitivity = 0.008;
    private const double HoverExtraDisplacement = 0.012;
    private const double CameraDistance = 4.6;

    private readonly SphereGeometry _geometry;
    private readonly SpherePhysics _physics;
    private readonly PerspectiveCamera _camera;
    private readonly PointLight _mouseLight;
    private readonly ModelVisual3D _sphereRoot;
    private MeshGeometry3D _tiledMesh = null!;
    private MeshGeometry3D _wireMesh = null!;
    private GeometryModel3D _tiledModel = null!;
    private GeometryModel3D _wireModel = null!;
    private readonly ObservableCollection<SphereGameTile> _tiles = new();

    private double _orbitYaw;
    private double _orbitPitch;
    private double _orbitVelocityYaw;
    private double _orbitVelocityPitch;
    private DateTime _lastFrameUtc = DateTime.UtcNow;
    private bool _isDragging;
    private Point _lastMouse;
    private int? _hoveredTileIndex;
    private long _frameCount;
    private DispatcherTimer? _fallbackTimer;

    /// <summary>帧计数（帧采样门断言用；60 帧采样门=1 秒内帧数 &gt;=20 规格底线）。</summary>
    public long FrameCount => _frameCount;

    /// <summary>渲染回调入口计数（测试可订阅 CompositionTarget 观测）。</summary>
    public event EventHandler? FrameRendered;

    /// <summary>贴图游戏瓦片（绑定后触发重建贴图面分配）。</summary>
    public static readonly DependencyProperty GameTilesProperty =
        DependencyProperty.Register(nameof(GameTiles), typeof(IReadOnlyList<SphereGameTile>),
            typeof(HomeSphereControl), new PropertyMetadata(null, OnGameTilesChanged));

    public IReadOnlyList<SphereGameTile>? GameTiles
    {
        get => (IReadOnlyList<SphereGameTile>?)GetValue(GameTilesProperty);
        set => SetValue(GameTilesProperty, value);
    }

    /// <summary>贴图点击命令（宿主页注入：跳该游戏 mod 选择页）。</summary>
    public static readonly DependencyProperty GameTileClickedProperty =
        DependencyProperty.Register(nameof(GameTileClicked), typeof(ICommand),
            typeof(HomeSphereControl), new PropertyMetadata(null));

    public ICommand? GameTileClicked
    {
        get => (ICommand?)GetValue(GameTileClickedProperty);
        set => SetValue(GameTileClickedProperty, value);
    }

    public HomeSphereControl()
    {
        InitializeComponent();
        _geometry = IcosahedronGeometry.Generate(Subdivision);
        _physics = new SpherePhysics(_geometry);

        // 相机：右下象限（x+/y-/z+ 看向球心）
        _camera = new PerspectiveCamera(
            new Point3D(2.2, -1.6, 3.6),
            new Vector3D(-2.2, 1.6, -3.6),
            new Vector3D(0, 1, 0), 45);

        // 鼠标光源（薄荷品牌色；2.8.3 条款）
        _mouseLight = new PointLight
        {
            Color = (Color)ColorConverter.ConvertFromString("#3ED598"),
            Range = 12.0,
            ConstantAttenuation = 1.0,
            LinearAttenuation = 0.15,
            QuadraticAttenuation = 0.02,
        };
        var lightModel = new ModelVisual3D { Content = new AmbientLight(Color.FromScRgb(0.28f, 1f, 1f, 1f)) };

        _sphereRoot = new ModelVisual3D();
        BuildSphereModels();

        SphereHost.Camera = _camera;
        SphereHost.Children.Add(lightModel);
        var lightHost = new ModelVisual3D { Content = _mouseLight };
        SphereHost.Children.Add(lightHost);
        SphereHost.Children.Add(_sphereRoot);

        Unloaded += OnUnloaded;
    }

    private static void OnGameTilesChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
    {
        if (d is HomeSphereControl c)
            c.AssignTiles();
    }

    /// <summary>分配贴图三角面（每游戏一个面簇；方形 UV 0-1 贴边）。</summary>
    private void AssignTiles()
    {
        _tiles.Clear();
        var trianglesPerTile = _geometry.TriangleCount;
        var tileCount = GameTiles?.Count ?? 0;

        if (GameTiles is null || tileCount == 0)
        {
            EmptyHint.Visibility = Visibility.Visible;
            RebuildTiledMesh(new Dictionary<int, int>());
            return;
        }
        EmptyHint.Visibility = Visibility.Collapsed;

        // 均分贴图面（避开重叠：每 tile 拿一组独立三角形）
        var perTile = Math.Max(1, Math.Min(24, trianglesPerTile / tileCount));
        var assignment = new Dictionary<int, int>();
        var tiles = new List<SphereGameTile>();
        for (var t = 0; t < tileCount; t++)
        {
            var baseTri = t * perTile;
            var tris = new List<int>(perTile);
            for (var k = 0; k < perTile; k++)
            {
                var tri = (baseTri + k) % _geometry.TriangleCount;
                tris.Add(tri);
                if (!assignment.ContainsKey(tri))
                    assignment[tri] = t;
            }
            tiles.Add((GameTiles[t]) with { AssignedTriangles = tris });
        }
        foreach (var t in tiles) _tiles.Add(t);
        RebuildTiledMesh(assignment);
    }

    /// <summary>重建贴图面网格（方形 UV 贴边）+线框面（半透明）。</summary>
    private void BuildSphereModels()
    {
        _wireMesh = new MeshGeometry3D();
        var pos = new Point3DCollection(_geometry.Positions.Count);
        for (var i = 0; i < _geometry.Positions.Count; i++)
            pos.Add(_geometry.Positions[i]);
        _wireMesh.Positions = pos;

        var idx = new Int32Collection(_geometry.TriangleIndices.Count);
        foreach (var t in _geometry.TriangleIndices)
            idx.Add(t);
        _wireMesh.TriangleIndices = idx;

        ComputeNormals(_wireMesh);

        // 无贴图区=透明（Alpha 0)：材质半透明描边色 + Emissive 线框观感
        _wireModel = new GeometryModel3D
        {
            Geometry = _wireMesh,
            Material = new DiffuseMaterial
            {
                Brush = new SolidColorBrush
                {
                    Color = Color.FromScRgb(0.18f, 0.75f, 0.87f, 0.81f),
                    Opacity = 0.18,
                },
            },
            BackMaterial = new DiffuseMaterial { Brush = Brushes.Transparent },
        };
        // Model3D 必须经 ModelVisual3D 包装才可入 Visual3D 树（Children:Visual3D)
        var wireHost = new ModelVisual3D { Content = _wireModel };
        _sphereRoot.Children.Add(wireHost);

        _tiledMesh = new MeshGeometry3D();
        RebuildTiledMesh(new Dictionary<int, int>());
        _tiledModel = new GeometryModel3D
        {
            Geometry = _tiledMesh,
            Material = new DiffuseMaterial { Brush = Brushes.White },
        };
        var tiledHost = new ModelVisual3D { Content = _tiledModel };
        _sphereRoot.Children.Add(tiledHost);
    }

    /// <summary>按贴图分配重建贴图面网格（方形 UV;未分配=空 TriangleIndices)。</summary>
    private void RebuildTiledMesh(IReadOnlyDictionary<int, int> assignment)
    {
        if (_tiledMesh is null) return;
        _tiledMesh.Positions = _wireMesh.Positions;
        var triIdx = new Int32Collection();
        var uvs = new PointCollection();
        // 方形裁剪贴边：每个贴图三角形 UV=(0,0),(1,0),(0,1) 三角填充方形左半
        for (var i = 0; i < _geometry.TriangleIndices.Count; i += 3)
        {
            var tri = i / 3;
            if (!assignment.ContainsKey(tri)) continue;
            triIdx.Add(_geometry.TriangleIndices[i]);
            triIdx.Add(_geometry.TriangleIndices[i + 1]);
            triIdx.Add(_geometry.TriangleIndices[i + 2]);
            uvs.Add(new Point(0, 0));
            uvs.Add(new Point(1, 0));
            uvs.Add(new Point(0, 1));
        }
        _tiledMesh.TriangleIndices = triIdx;
        _tiledMesh.TextureCoordinates = uvs;
        ComputeNormals(_tiledMesh);
        if (_tiledModel is not null)
        {
            // 贴图=首个瓦片图标（多图集留 D5.x 图集合并；KISS 起点单图）
            _tiledModel.Material = _tiles.Count > 0 && _tiles[0].Icon is not null
                ? new DiffuseMaterial { Brush = new ImageBrush(_tiles[0].Icon!) }
                : new DiffuseMaterial { Brush = new SolidColorBrush(Color.FromScRgb(0.9f, 0.24f, 0.84f, 0.6f)) };
        }
    }

    private static void ComputeNormals(MeshGeometry3D mesh)
    {
        // 球径法向=顶点归一化方向（v1.4 §2.8.1 远暗近亮=顶点色，法向同源）
        var normals = new Vector3DCollection(mesh.Positions.Count);
        for (var i = 0; i < mesh.Positions.Count; i++)
        {
            var p = mesh.Positions[i];
            var v = new Vector3D(p.X, p.Y, p.Z);
            v.Normalize();
            normals.Add(v);
        }
        mesh.Normals = normals;
    }

    /// <summary>启动逐帧循环（CompositionTarget.Rendering;沙箱无桌面合成时 DispatcherTimer fallback)。</summary>
    public void StartAnimation()
    {
        CompositionTarget.Rendering += OnRender;
        _fallbackTimer = new DispatcherTimer(DispatcherPriority.Background)
        {
            Interval = TimeSpan.FromMilliseconds(50),
        };
        _fallbackTimer.Tick += (s, e) => OnRender(s, EventArgs.Empty);
        _fallbackTimer.Start();
        _lastFrameUtc = DateTime.UtcNow;
    }

    private void OnUnloaded(object sender, RoutedEventArgs e)
    {
        CompositionTarget.Rendering -= OnRender;
        _fallbackTimer?.Stop();
    }

    private void OnRender(object? sender, EventArgs e)
    {
        var now = DateTime.UtcNow;
        var dt = (now - _lastFrameUtc).TotalSeconds;
        _lastFrameUtc = now;
        if (dt <= 0 || dt > 0.25) dt = 1.0 / 60.0;

        // 自转（拖拽期间暂停=用户输入优先）
        if (!_isDragging)
        {
            _orbitYaw += AutoRotateRadiansPerSecond * dt;
        }

        // 拖拽惯性
        _orbitYaw += _orbitVelocityYaw * dt;
        _orbitPitch += _orbitVelocityPitch * dt;
        _orbitVelocityYaw *= OrbitFriction;
        _orbitVelocityPitch *= OrbitFriction;
        if (Math.Abs(_orbitVelocityYaw) < 1e-5) _orbitVelocityYaw = 0;
        if (Math.Abs(_orbitVelocityPitch) < 1e-5) _orbitVelocityPitch = 0;
        ClampPitch();

        // 物理推进（鼠标光源位置=世界系）
        var mouseWorld = _mouseLight.Position;
        _physics.Step(dt, new Point3D(mouseWorld.X, mouseWorld.Y, mouseWorld.Z));

        ApplyDeformation();
        ApplyCameraTransform();

        _frameCount++;
        FrameRendered?.Invoke(this, EventArgs.Empty);
    }

    private void ApplyDeformation()
    {
        var positions = _wireMesh.Positions;
        for (var i = 0; i < positions.Count; i++)
        {
            var p = _physics.CurrentPosition(i);
            // hover 放大：悬停瓦片的三角形顶点沿法向额外推（视觉 1.12 近似）
            var extra = 0.0;
            if (_hoveredTileIndex is { } tileIdx && _tiles.Count > 0)
            {
                var tile = _tiles[tileIdx];
                foreach (var tri in tile.AssignedTriangles)
                {
                    var baseIdx = tri * 3;
                    if (baseIdx < _geometry.TriangleIndices.Count
                        && (_geometry.TriangleIndices[baseIdx] == i
                            || _geometry.TriangleIndices[baseIdx + 1] == i
                            || _geometry.TriangleIndices[baseIdx + 2] == i))
                    {
                        extra = HoverExtraDisplacement;
                        break;
                    }
                }
            }
            var n = new Vector3D(p.X, p.Y, p.Z);
            n.Normalize();
            positions[i] = new Point3D(
                p.X + n.X * extra,
                p.Y + n.Y * extra,
                p.Z + n.Z * extra);
        }
    }

    private void ApplyCameraTransform()
    {
        // 轨道旋转（绕球心；标准球面坐标：yaw 绕 Y、pitch 绕 XZ 平面）
        var cosP = Math.Cos(_orbitPitch);
        var x = CameraDistance * cosP * Math.Sin(_orbitYaw);
        var y = CameraDistance * Math.Sin(_orbitPitch);
        var z = CameraDistance * cosP * Math.Cos(_orbitYaw);
        _camera.Position = new Point3D(x, y, z);
        _camera.LookDirection = new Vector3D(-x, -y, -z);
    }

    private void ClampPitch()
    {
        const double maxPitch = Math.PI / 3.0;
        if (_orbitPitch > maxPitch) _orbitPitch = maxPitch;
        if (_orbitPitch < -maxPitch) _orbitPitch = -maxPitch;
    }

    protected override void OnMouseMove(MouseEventArgs e)
    {
        base.OnMouseMove(e);
        var pos = e.GetPosition(this);

        if (_isDragging)
        {
            var dx = pos.X - _lastMouse.X;
            var dy = pos.Y - _lastMouse.Y;
            _orbitVelocityYaw = dx * OrbitSensitivity;
            _orbitVelocityPitch = -dy * OrbitSensitivity;
        }
        else
        {
            // 鼠标=PointLight 光源（投影到球前平面 z=1.2)
            var w = ActualWidth > 0 ? ActualWidth : 800;
            var h = ActualHeight > 0 ? ActualHeight : 600;
            var lx = (pos.X / w - 0.5) * 4.0;
            var ly = (0.5 - pos.Y / h) * 3.0;
            _mouseLight.Position = new Point3D(lx, ly, 1.6);
        }

        _lastMouse = pos;
        UpdateHover(pos);
    }

    protected override void OnMouseLeftButtonDown(MouseButtonEventArgs e)
    {
        base.OnMouseLeftButtonDown(e);
        _isDragging = true;
        _lastMouse = e.GetPosition(this);
        CaptureMouse();
    }

    protected override void OnMouseLeftButtonUp(MouseButtonEventArgs e)
    {
        base.OnMouseLeftButtonUp(e);
        var wasDragging = _isDragging;
        _isDragging = false;
        ReleaseMouseCapture();

        // 点击（拖拽距离小=点击语义）
        var pos = e.GetPosition(this);
        var moved = Math.Abs(pos.X - _lastMouse.X) + Math.Abs(pos.Y - _lastMouse.Y);
        if (wasDragging && moved < 6)
        {
            var hit = HitTestTile(pos);
            if (hit.HasValue && GameTileClicked?.CanExecute(hit.Value) == true)
                GameTileClicked.Execute(hit.Value);
        }
    }

    /// <summary>命中贴图瓦片（RayHitTest;返回贴图瓦片索引）。</summary>
    private int? HitTestTile(Point screenPos)
    {
        var foundTri = HitTriangleOnMesh(_tiledMesh, screenPos);
        return FindTileOfTriangle(foundTri);
    }

    /// <summary>
    /// 命中指定网格的三角形索引（Viewport3D RayHitTest)。
    /// WPF RayMeshGeometry3DHitTestResult 只暴露 VertexIndex1-3(顶点索引，无
    /// TriangleIndex)=按顶点集合反查 TriangleIndices 中的三角形序号。
    /// </summary>
    private int? HitTriangleOnMesh(MeshGeometry3D mesh, Point screenPos)
    {
        int? found = null;
        VisualTreeHelper.HitTest(SphereHost, null, (HitTestResult result) =>
        {
            if (result is System.Windows.Media.Media3D.RayMeshGeometry3DHitTestResult rayHit
                && ReferenceEquals(rayHit.MeshHit, mesh))
            {
                found = TriangleFromVertices(mesh,
                    rayHit.VertexIndex1, rayHit.VertexIndex2, rayHit.VertexIndex3);
                return HitTestResultBehavior.Stop;
            }
            return HitTestResultBehavior.Continue;
        }, new PointHitTestParameters(screenPos));
        return found;
    }

    /// <summary>顶点集合匹配三角形序号（集合相等=同三角形，顺序无关）。</summary>
    private static int? TriangleFromVertices(MeshGeometry3D mesh, int v1, int v2, int v3)
    {
        var indices = mesh.TriangleIndices;
        for (var i = 0; i + 2 < indices.Count; i += 3)
        {
            var a = indices[i];
            var b = indices[i + 1];
            var c = indices[i + 2];
            if ((a == v1 || a == v2 || a == v3)
                && (b == v1 || b == v2 || b == v3)
                && (c == v1 || c == v2 || c == v3)
                && a != b && a != c && b != c)
                return i / 3;
        }
        return null;
    }

    private void UpdateHover(Point screenPos)
    {
        var tri = HitTriangleOnMesh(_tiledMesh, screenPos);
        var tileIdx = FindTileOfTriangle(tri);
        if (tileIdx != _hoveredTileIndex)
        {
            _hoveredTileIndex = tileIdx;
            if (tileIdx.HasValue && _tiles.Count > tileIdx.Value)
            {
                GameBubbleText.Text = _tiles[tileIdx.Value].Title;
                GameBubble.Visibility = Visibility.Visible;
                // 泡泡位置=跟随命中点（命中点屏幕投影）
                var bubblePos = screenPos;
                GameBubble.Margin = new Thickness(
                    Math.Max(4, bubblePos.X - 60), Math.Max(4, bubblePos.Y - 44), 0, 0);
            }
            else
            {
                // 移开复原（对话泡泡消失）
                GameBubble.Visibility = Visibility.Collapsed;
            }
        }
    }

    private int? FindTileOfTriangle(int? triangle)
    {
        if (!triangle.HasValue) return null;
        for (var t = 0; t < _tiles.Count; t++)
        {
            if (_tiles[t].AssignedTriangles.Contains(triangle.Value))
                return t;
        }
        return null;
    }
}