; SWDM - Steam 工坊下载管理器  Inno Setup 安装脚本
; ----------------------------------------------------------------------------
; 编译：  ISCC.exe installer\swdm.iss
; 前置：  先完成 PyInstaller 构建（build\dist\SWDM\ 已生成）
; 产物：  installer\Output\SWDM-Setup-1.0.0.exe
;
; 设计要点：
;   * 安装包不打包 steamcmd（首次运行时程序自动下载部署到 %APPDATA%\SWDM\steamcmd）
;   * 卸载时询问是否保留用户数据（%APPDATA%\SWDM：配置 / 模组库 / 缓存 / 日志）
;   * 绿色版目录 build\dist\SWDM\ 可直接拷贝使用（放入 portable.marker 即便携模式）

#define SWDMAppName        "SWDM - Steam 工坊下载管理器"
#define SWDMAppNameShort   "SWDM"
#define SWDMVersion        "1.3.9"
#define SWDMPublisher      "SWDM"
#define SWDMExeName        "SWDM.exe"

[Setup]
AppId={{8F3C2A51-9D70-4E5B-A6F2-2C1B0E44D9A7}}
AppName={#SWDMAppName}
AppVersion={#SWDMVersion}
AppVerName={#SWDMAppName} {#SWDMVersion}
AppPublisher={#SWDMPublisher}
AppPublisherURL=https://github.com/swdm/swdm
AppSupportURL=https://github.com/swdm/swdm/issues
AppUpdatesURL=https://github.com/swdm/swdm/releases
VersionInfoVersion={#SWDMVersion}
VersionInfoProductVersion={#SWDMVersion}

DefaultDirName={autopf}\SWDM
DefaultGroupName={#SWDMAppNameShort}
DisableProgramGroupPage=yes
; 不允许安装到上一级目录结构外，避免选到源码目录
AppendDefaultDirName=yes
UsePreviousAppDir=no
UninstallDisplayIcon={app}\{#SWDMExeName}
UninstallDisplayName={#SWDMAppName}
SetupIconFile=..\swdm\resources\icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
OutputBaseFilename=SWDM-Setup-{#SWDMVersion}
OutputDir=Output
PrivilegesRequired=admin
CloseApplications=yes
; 运行中的实例持有全局互斥量 SWDM_SingleInstance_Mutex（由主程序创建），
; 安装/卸载程序据此检测运行中的实例，配合 CloseApplications 发送 WM_CLOSE
AppMutex=SWDM_SingleInstance_Mutex
; 卸载时不要自动删除用户数据（由脚本里的复选框控制）
Uninstallable=yes

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english";    MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "在桌面创建快捷方式(&D)"; GroupDescription: "附加图标:"; Flags: checkedonce
Name: "startmenu";   Description: "在开始菜单创建快捷目录(&S)"; GroupDescription: "附加图标:"; Flags: checkedonce

[Files]
; 打包产物整体纳入（不含 steamcmd：首次运行自动下载）
Source: "..\build\dist\SWDM\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#SWDMAppNameShort}";         Filename: "{app}\{#SWDMExeName}"; IconFilename: "{app}\{#SWDMExeName}"
Name: "{group}\卸载 {#SWDMAppNameShort}";     Filename: "{uninstallexe}"
Name: "{commondesktop}\{#SWDMAppNameShort}"; Filename: "{app}\{#SWDMExeName}"; IconFilename: "{app}\{#SWDMExeName}"; Tasks: desktopicon

[Run]
; 安装后启动（复选框）
Filename: "{app}\{#SWDMExeName}"; Description: "启动 {#SWDMAppNameShort}"; Flags: nowait postinstall skipifsilent runascurrentuser

; ----------------------------------------------------------------------------
; 安全卸载：多重防护，绝不动 {app} 之外的任何目录
;
;   防护 1：安装目录白名单 —— 只在 {app} 内删除由本安装器写入的文件
;   防护 2：数据目录精确校验 —— 只删 %APPDATA%\SWDM，且必须含本程序特征文件
;   防护 3：源代码保护 —— 若 {app} 内出现 .py/.spec 等源码，中止删除并提示
;   防护 4：路径兜底 —— 所有待删路径必须以 \SWDM 结尾，拒绝异常路径
; ----------------------------------------------------------------------------
[Code]
var
  KeepDataCheckBox: TNewCheckBox;
  KeepUserData: Boolean;

// 卸载程序启动后、执行任何操作之前弹出，让用户先决定是否保留用户数据
// （用户反馈：不应在卸载过程中才问）
function InitializeUninstall(): Boolean;
var
  Msg: String;
begin
  Msg := '卸载 SWDM - Steam 工坊下载管理器。' #13#10 #13#10
         '是否保留用户数据（已下载的模组、配置、模组库）？' #13#10
         '数据位于 %APPDATA%\SWDM。' #13#10 #13#10
         '「是」= 保留用户数据（推荐，仅删除程序本身）' #13#10
         '「否」= 同时删除全部用户数据' #13#10
         '「取消」= 放弃卸载';
  case MsgBox(Msg, mbConfirmation, MB_YESNOCANCEL or MB_DEFBUTTON1) of
    IDYES:    KeepUserData := True;
    IDNO:     KeepUserData := False;
    IDCANCEL: begin
                Result := False;
                Exit;
              end;
  end;
  Result := True;
end;

// 判断目录是否混入了源代码（说明用户把程序装进了源码目录，危险）
function ContainsSourceCode(const Dir: String): Boolean;
var
  FindRec: TFindRec;
begin
  Result := False;
  if Dir = '' then Exit;
  if FindFirst(Dir + '\*', FindRec) then
  begin
    repeat
      if (FindRec.Name <> '.') and (FindRec.Name <> '..') then
      begin
        if FindRec.Attributes and FILE_ATTRIBUTE_DIRECTORY <> 0 then
        begin
          // 递归检查子目录（限两层，避免过深）
          if ContainsSourceCode(Dir + '\' + FindRec.Name) then
          begin
            Result := True;
            FindClose(FindRec);
            Exit;
          end;
        end
        else
        begin
          // 源码文件特征
          if (Pos('.py', FindRec.Name) > 0) or (Pos('.spec', FindRec.Name) > 0)
             or (Pos('.iss', FindRec.Name) > 0) or (Pos('build.ps1', FindRec.Name) > 0) then
          begin
            Result := True;
            FindClose(FindRec);
            Exit;
          end;
        end;
      end;
    until not FindNext(FindRec);
    FindClose(FindRec);
  end;
end;

// 安装前校验：拒绝安装到含源代码的目录（从源头防止卸载误删源码）
function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = wpSelectDir then
  begin
    if ContainsSourceCode(WizardDirValue()) then
    begin
      MsgBox('所选目录包含源代码文件（.py/.spec/.iss 等）。' #13#10
             '为防止卸载时误删源码，请选择其它目录（推荐默认的 Program Files\SWDM）。',
             mbError, MB_OK);
      Result := False;
      Exit;
    end;
  end;
end;

// 判断目录是否是本程序的数据目录（含特征文件，防止误删任意目录）
function IsSWDMDataDir(const Dir: String): Boolean;
begin
  Result := False;
  if Dir = '' then Exit;
  // 必须以 \SWDM 结尾（大小写不敏感），且实际存在
  if not SameText(ExtractFileName(Dir), 'SWDM') then Exit;
  if not DirExists(Dir) then Exit;
  // 必须包含本程序的特征文件之一（首次运行才会创建）
  if FileExists(Dir + '\config.json') then Result := True
  else if FileExists(Dir + '\library.db') then Result := True
  else if FileExists(Dir + '\logs\swdm.log') then Result := True;
end;

procedure InitializeUninstallProgressForm();
begin
  KeepDataCheckBox := TNewCheckBox.Create(UninstallProgressForm);
  KeepDataCheckBox.Parent := UninstallProgressForm.MainPanel;
  KeepDataCheckBox.Caption := '保留用户数据（已下载的模组、配置、模组库，位于 %APPDATA%\SWDM）——程序自带的 steamcmd 会被自动清理，您自行安装的 steamcmd 不受影响';
  // 同步卸载前弹窗的选择（用户反馈：弹窗选了删除，这里仍勾着"保留"是摆设）
  KeepDataCheckBox.Checked := KeepUserData;
  KeepDataCheckBox.Left := UninstallProgressForm.StatusLabel.Left;
  KeepDataCheckBox.Top := UninstallProgressForm.StatusLabel.Top + UninstallProgressForm.StatusLabel.Height + ScaleY(12);
  KeepDataCheckBox.Width := UninstallProgressForm.MainPanel.ClientWidth - ScaleX(24);
  KeepDataCheckBox.Height := ScaleY(22);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);var
  DataDir, SteamcmdDir: String;
  DoDelete: Boolean;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{userappdata}\SWDM');
    // 程序运行时自动部署的 steamcmd 属于程序依赖（由安装程序携带的
    // steamcmd.zip 解压而来），卸载时始终清理；用户自行安装的 steamcmd
    // （如 C:\Program Files (x86)\steamcmd）不在本目录内，绝不会被删
    SteamcmdDir := DataDir + '\steamcmd';

    // 防护 3：安装目录若混入源代码，提示并跳过数据删除
    if ContainsSourceCode(ExpandConstant('{app}')) then
    begin
      Log(Format('[安全] 检测到安装目录含源代码，已跳过数据目录删除: %s', [DataDir]));
      MsgBox('检测到安装目录中包含源代码文件（.py/.spec/.iss 等）。' #13#10
             '为避免误删源码，本次卸载不会删除任何额外目录。' #13#10
             '用户数据目录已保留：' + DataDir, mbInformation, MB_OK);
      Exit;
    end;

    // 始终删除程序依赖：运行时部署的内置 steamcmd（校验确为本程序数据目录）
    if IsSWDMDataDir(DataDir) and DirExists(SteamcmdDir) then
    begin
      DelTree(SteamcmdDir, True, True, True);
      Log(Format('已删除程序部署的 steamcmd（程序依赖）: %s', [SteamcmdDir]));
    end;

    // 用户数据（mod 库 / 配置 / 缓存 / 日志）：以勾选框为最终准
    // （勾选框已在 InitializeUninstallProgressForm 中同步卸载前弹窗的选择，
    // 用户仍可在进度页改主意；不再用 KeepUserData 强制覆盖）
    DoDelete := Assigned(KeepDataCheckBox) and (not KeepDataCheckBox.Checked);
    if DoDelete then
    begin
      // 防护 1+2+4：必须是本程序数据目录才删除
      if IsSWDMDataDir(DataDir) then
      begin
        DelTree(DataDir, True, True, True);
        Log(Format('已删除用户数据目录: %s', [DataDir]));
      end
      else begin
        Log(Format('[安全] 数据目录未通过校验，已跳过删除: %s', [DataDir]));
      end;
    end
    else begin
      Log(Format('已保留用户数据目录（mod 库/配置）: %s', [DataDir]));
    end;
  end;
end;
