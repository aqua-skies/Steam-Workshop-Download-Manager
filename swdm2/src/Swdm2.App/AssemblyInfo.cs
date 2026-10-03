using System.Runtime.CompilerServices;
using System.Windows;

// D5.15:UiTests 访问 x:Name 生成的 internal 控件字段（EmptyHint/GameBubble)
[assembly: InternalsVisibleTo("Swdm2.UiTests")]

[assembly:ThemeInfo(
    ResourceDictionaryLocation.None,            //where theme specific resource dictionaries are located
                                                //(used if a resource is not found in the page,
                                                // or application resource dictionaries)
    ResourceDictionaryLocation.SourceAssembly   //where the generic resource dictionary is located
                                                //(used if a resource is not found in the page,
                                                // app, or any theme specific resource dictionaries)
)]
