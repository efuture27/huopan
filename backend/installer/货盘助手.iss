; ============================================================================
;  货盘助手 · Windows 安装包脚本（Inno Setup 6）
;
;  编译：ISCC.exe 货盘助手.iss
;  产物：<项目根>\货盘助手_安装程序_v7.17.exe
;
;  设计要点：
;   - 标准安装（所有用户），装到 C:\Program Files\货盘助手，需一次 UAC
;   - 安装向导里可选「数据目录」（默认 %LOCALAPPDATA%\货盘助手\data）
;     选择结果写入 {app}\.env 的 HUOPAN_DATA_DIR，程序启动时读取
;   - 程序目录只读，所有运行期数据（数据库/上传原件/日志）都在数据目录
;   - WebView2 缺失时自动联网安装（失败不影响使用，程序会回退浏览器模式）
;   - 卸载时询问是否保留数据（默认保留）
;
;  注意：本文件必须保存为 UTF-8 with BOM，否则中文会乱码。
; ============================================================================

#define AppName "货盘助手"
#define AppVersion "7.17"
#define AppVerName "货盘助手 7.17"
#define AppExeName "货盘助手.exe"
#define AppPublisher "货盘助手"
#define DistDir "..\dist\货盘助手"
#define WebView2Guid "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"

[Setup]
AppId={{8E1D6F3A-1B2C-4D5E-9F01-2A3B4C5D6E7F}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppVerName}
AppPublisher={#AppPublisher}
VersionInfoVersion=7.17.0.0
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} 安装程序
VersionInfoProductName={#AppName}
VersionInfoProductVersion={#AppVersion}

; 所有用户安装 → C:\Program Files\货盘助手
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
AllowNoIcons=yes
PrivilegesRequired=admin

OutputDir=..\..
OutputBaseFilename=货盘助手_安装程序_v7.17
SetupIconFile=..\app_icon.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}

Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Python 3.11 运行库要求 Windows 8.1+
MinVersion=6.3

; 覆盖安装/卸载前自动关闭正在运行的货盘助手（Restart Manager + 代码里 taskkill 双重保险）
CloseApplications=yes
CloseApplicationsFilter=*.exe
RestartApplications=no

[Languages]
Name: "chinesesimplified"; MessagesFile: "Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："; Flags: checkedonce
Name: "firewall"; Description: "放行 Windows 防火墙（同事用浏览器访问本机时需要）"; GroupDescription: "附加任务："; Flags: checkedonce
Name: "autostart"; Description: "开机自动启动（登录后自动在后台运行）"; GroupDescription: "附加任务："; Flags: unchecked

[Files]
; 整个程序目录。排除 data（数据库改在数据目录里由程序自动创建，不放进 Program Files）
Source: "{#DistDir}\*"; DestDir: "{app}"; Excludes: "data\*,.env,服务日志.log,同事访问地址.txt"; Flags: ignoreversion recursesubdirs createallsubdirs
; WebView2 联网引导器：安装时按需运行，用完即删
Source: "deps\MicrosoftEdgeWebView2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\使用说明"; Filename: "{app}\使用说明.txt"
Name: "{group}\卸载 {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Registry]
; 数据目录指针记录一份到注册表：注册表是 Unicode，中文路径不会乱码，卸载时用它询问「是否删除数据」
Root: HKLM; Subkey: "SOFTWARE\{#AppName}"; ValueType: string; ValueName: "DataDir"; ValueData: "{code:GetDataDir}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#AppName}"; ValueData: """{app}\{#AppExeName}"""; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{tmp}\MicrosoftEdgeWebView2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "正在安装界面组件（WebView2 运行时）..."; Flags: runhidden waituntilterminated; Check: WebView2Missing
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""{#AppName}"""; Flags: runhidden; Tasks: firewall
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""{#AppName}"" dir=in action=allow program=""{app}\{#AppExeName}"" enable=yes profile=any"; StatusMsg: "正在放行 Windows 防火墙..."; Flags: runhidden; Tasks: firewall
Filename: "{app}\{#AppExeName}"; Description: "立即运行 {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""{#AppName}"""; Flags: runhidden; RunOnceId: "DelFirewallRule"
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM {#AppExeName}"; Flags: runhidden; RunOnceId: "KillApp"

[UninstallDelete]
Type: files; Name: "{app}\install_mode.txt"
Type: filesandordirs; Name: "{app}\__pycache__"

[Code]
var
  DataDirPage: TInputDirWizardPage;
  GDataDir: String;          { 卸载时用来询问是否删除数据 }

{ ---------- 命令行 /DATADIR=xxx 支持（静默安装、批量部署用） ---------- }
function GetDataDirParam(): String;
var
  i: Integer;
  p: String;
begin
  Result := '';
  for i := 1 to ParamCount do
  begin
    p := ParamStr(i);
    if Pos('/DATADIR=', Uppercase(p)) = 1 then
      Result := Copy(p, Length('/DATADIR=') + 1, Length(p));
  end;
end;

{ ---------- 通用：命令行里有没有带某个开关 ---------- }
function HasParam(Name: String): Boolean;
var
  i: Integer;
begin
  Result := False;
  for i := 1 to ParamCount do
    if Uppercase(ParamStr(i)) = Uppercase(Name) then
      Result := True;
end;

{ ---------- 数据目录向导页 ---------- }
procedure InitializeWizard();
var
  Def: String;
begin
  Def := ExpandConstant('{localappdata}\{#AppName}\data');
  if GetDataDirParam() <> '' then
    Def := GetDataDirParam();

  DataDirPage := CreateInputDirPage(wpSelectTasks,
    '数据文件存放位置',
    '货盘助手的数据库、上传的成本表放在哪里？',
    '建议保持默认（你自己的用户目录，普通账号即可读写）。' + #13#10 +
    '如需放在 D 盘等位置，点「浏览」选择，或直接修改下面的路径。',
    False, '');
  DataDirPage.Add('数据目录：');
  DataDirPage.Values[0] := Def;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (DataDirPage <> nil) and (CurPageID = DataDirPage.ID) then
  begin
    if Trim(DataDirPage.Values[0]) = '' then
    begin
      MsgBox('请填写数据目录。', mbError, MB_OK);
      Result := False;
    end
    else if Pos(':\PROGRAM FILES', Uppercase(DataDirPage.Values[0])) > 0 then
    begin
      MsgBox('数据目录不能放在 Program Files 里（程序运行时会写不进去）。' + #13#10 +
             '请换一个位置，例如 D:\货盘数据。', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

{ ---------- 安装：写入数据目录指向 ---------- }
{ [Registry] 里的 ValueData 用这个函数取值（脚本常量的原型必须是 Param: String） }
function GetDataDir(Param: String): String;
begin
  if Trim(DataDirPage.Values[0]) <> '' then
    Result := Trim(DataDirPage.Values[0])
  else
    Result := ExpandConstant('{localappdata}\{#AppName}\data');
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  Lines: TArrayOfString;
begin
  if CurStep = ssInstall then
  begin
    { 覆盖安装时先结束正在运行的程序，避免文件被占用 }
    Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM {#AppExeName}', '',
         SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;

  if CurStep = ssPostInstall then
  begin
    { 安装标记：程序靠它判断「我是安装版」，从而去用户目录取数据，
      而不是把数据写在只读的 Program Files 里。绝不能靠 data_dir.txt 判断——
      那个文件在用户目录，是机器级的，会劫持绿色版/源码运行的数据目录 }
    SaveStringToFile(ExpandConstant('{app}\install_mode.txt'),
                     'installed' + #13#10, False);

    { 程序启动时读这个文件决定数据放哪（UTF-8 写，中文路径不会乱码） }
    Lines := [GetDataDir('')];
    ForceDirectories(ExpandConstant('{localappdata}\{#AppName}'));
    SaveStringsToUTF8File(ExpandConstant('{localappdata}\{#AppName}\data_dir.txt'),
                          Lines, False);
  end;
end;

{ ---------- WebView2 检测 ---------- }
function WebView2Missing(): Boolean;
var
  v: String;
begin
  Result := True;
  if RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{#WebView2Guid}', 'pv', v) and (v <> '') and (v <> '0.0.0.0') then
    Result := False
  else if RegQueryStringValue(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{#WebView2Guid}', 'pv', v) and (v <> '') and (v <> '0.0.0.0') then
    Result := False
  else if RegQueryStringValue(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{#WebView2Guid}', 'pv', v) and (v <> '') and (v <> '0.0.0.0') then
    Result := False;
end;

{ ---------- 卸载 ---------- }
{ 从注册表读数据目录（Unicode，中文路径可靠；文件是 UTF-8，Pascal 里只能按 ANSI 读会乱码） }
function InitializeUninstall(): Boolean;
var
  v: String;
begin
  GDataDir := '';
  if RegQueryStringValue(HKLM, 'SOFTWARE\{#AppName}', 'DataDir', v) then
    GDataDir := Trim(v);
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  PtrDir: String;
  Removed: Boolean;
  DoDelete: Boolean;
  Purge: Boolean;
  SilentRun: Boolean;
begin
  { 卸载收尾：问用户要不要连数据一起删；删的话把「数据目录指针」和空壳父目录也收掉 }
  if CurUninstallStep <> usPostUninstall then
    Exit;

  { 静默彻底清理：先设环境变量 HUOPAN_PURGE_DATA=1 再运行卸载程序。
    注意不能用自定义命令行开关（如 /DELDATA）——Inno 的卸载程序会把自己
    复制到临时目录再启动，只转发它认识的参数，自定义参数会被丢掉。 }
  Purge := (ExpandConstant('{%HUOPAN_PURGE_DATA}') = '1');
  SilentRun := HasParam('/SILENT') or HasParam('/VERYSILENT');
  DoDelete := Purge;

  { 数据目录还在、且不是强制清理 → 问用户一句 }
  if (not Purge) and (GDataDir <> '') and DirExists(GDataDir) then
    DoDelete := (MsgBox('是否同时删除数据文件？' + #13#10 + #13#10 +
                        GDataDir + #13#10 + #13#10 +
                        '选择「否」将保留你的商品库、已生成的货盘和上传记录，' + #13#10 +
                        '下次重新安装还能继续使用。',
                        mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES);

  if DoDelete then
  begin
    Removed := True;
    if (GDataDir <> '') and DirExists(GDataDir) then
      Removed := DelTree(GDataDir, True, True, True);

    { 数据删了（或本来就没跑过、数据目录不存在）→ 指针文件也一并清掉，
      再顺手收掉空掉的父文件夹，避免卸载后还在用户目录里留个空壳 }
    DeleteFile(ExpandConstant('{localappdata}\{#AppName}\data_dir.txt'));
    PtrDir := ExpandConstant('{localappdata}\{#AppName}');
    if DirExists(PtrDir) then
      RemoveDir(PtrDir);   { 只删空目录；里面还有别的东西就原样留着 }

    if SilentRun then
      Exit;

    if Removed then
      MsgBox('数据文件已删除，已彻底清理干净。', mbInformation, MB_OK)
    else
      MsgBox('部分数据文件删除失败（可能仍被占用），请手动删除：' + #13#10 + GDataDir,
             mbError, MB_OK);
  end
  else if (GDataDir <> '') and DirExists(GDataDir) and (not SilentRun) then
    MsgBox('已保留数据文件，位置：' + #13#10 + #13#10 + GDataDir + #13#10 + #13#10 +
           '以后想彻底清理，删掉这个文件夹即可。', mbInformation, MB_OK);
end;
