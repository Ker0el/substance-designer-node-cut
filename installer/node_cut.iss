; Node Cut —— Substance 3D Designer 插件安装包

#define AppName     "Node Cut"
#define AppVer      "1.0.3"
#define AppVerQuad  "1.0.3.0"
#define AppId       "{A5BFF457-8165-4116-BE28-319A7AADB237}"
#define Publisher   "Ker0el"

[Setup]
AppId={{#AppId}
AppName={#AppName}
AppVersion={#AppVer}
AppVerName={#AppName} {#AppVer}
AppPublisher={#Publisher}
DefaultDirName={userdocs}\Adobe\Adobe Substance 3D Designer\python\sduserplugins\node_cut
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableWelcomePage=yes
UsePreviousAppDir=no
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=
OutputDir=output
OutputBaseFilename=NodeCut-Setup_v{#AppVer}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=no
RestartApplications=no
AllowNoIcons=yes
InfoBeforeFile=说明.rtf
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#AppName} {#AppVer}
VersionInfoVersion={#AppVerQuad}
VersionInfoProductName={#AppName}
VersionInfoDescription={#AppName} 安装包

[Languages]
Name: "cn"; MessagesFile: "ChineseSimplified.isl"

[Messages]
cn.FinishedLabel=插件已经装好了，但还不会生效 —— 请现在启动（或重新启动）Substance 3D Designer。%n%n打开任意一个 Substance 图形，图形视图工具栏末尾出现剪刀按钮，就说明加载成功了。
cn.FinishedLabelNoIcons=插件已经装好了，但还不会生效 —— 请现在启动（或重新启动）Substance 3D Designer。%n%n打开任意一个 Substance 图形，图形视图工具栏末尾出现剪刀按钮，就说明加载成功了。
cn.ClickFinish=点击“完成”退出安装程序。

[Files]
Source: "payload\node_cut\pluginInfo.json"; DestDir: "{app}";          Flags: ignoreversion
Source: "payload\node_cut\node_cut\*.py";   DestDir: "{app}\node_cut"; Flags: ignoreversion

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
const
  DesignerExeName    = 'Adobe Substance 3D Designer.exe';
  CrashReporterName  = 'AdobeCrashReportWindow.exe';
  UninstallRegPath   = 'Software\Microsoft\Windows\CurrentVersion\Uninstall';

var
  gDesignerDir: String;
  gDesignerProbed: Boolean;

function CreateFileW(lpFileName: String; dwDesiredAccess, dwShareMode: DWORD;
  lpSecurityAttributes: DWORD; dwCreationDisposition, dwFlagsAndAttributes: DWORD;
  hTemplateFile: DWORD): DWORD; external 'CreateFileW@kernel32.dll stdcall';
function GetLastError(): DWORD; external 'GetLastError@kernel32.dll stdcall';
function CloseHandle(h: DWORD): LongBool; external 'CloseHandle@kernel32.dll stdcall';

// 判据：能不能以「读写 + 不共享」打开。
// err=32 是 ERROR_SHARING_VIOLATION —— 正在跑的 exe 不允许别人改它，
// 这就是「这个程序在不在跑」最准的判据，不依赖进程枚举。
function BusyReason(const Path: String): String;
var
  H: DWORD;
begin
  Result := '';
  if not FileExists(Path) then Exit;
  H := CreateFileW(Path, $C0000000, 0, 0, 3, 0, 0);
  if H = $FFFFFFFF then
  begin
    if GetLastError() = 32 then
      Result := '被占用';
  end
  else
    CloseHandle(H);
end;

// Painter / Sampler / Stager 的名字里也带 Substance，别认错
function IsDesignerName(const Name: String): Boolean;
begin
  Result := (Pos('Substance Designer', Name) > 0) or
            (Pos('Substance 3D Designer', Name) > 0);
  if Result and ((Pos('Painter', Name) > 0) or
                 (Pos('Sampler', Name) > 0) or
                 (Pos('Stager', Name) > 0)) then
    Result := False;
end;

// Designer 装在哪只能从注册表卸载项反查。这台机器上它装在 E:\ 这种非常规位置，
// 硬猜路径必然猜不到。
function FindDesignerDir(): String;
var
  Roots: array[0..2] of Integer;
  Names: TArrayOfString;
  I, J: Integer;
  Name, Loc: String;
begin
  Result := '';
  Roots[0] := HKLM64;
  Roots[1] := HKLM32;
  Roots[2] := HKCU;

  for I := 0 to 2 do
  begin
    if not RegGetSubkeyNames(Roots[I], UninstallRegPath, Names) then
      Continue;
    for J := 0 to GetArrayLength(Names) - 1 do
    begin
      if not RegQueryStringValue(Roots[I], UninstallRegPath + '\' + Names[J],
                                 'DisplayName', Name) then
        Continue;
      if not IsDesignerName(Name) then
        Continue;
      if not RegQueryStringValue(Roots[I], UninstallRegPath + '\' + Names[J],
                                 'InstallLocation', Loc) then
        Continue;
      if (Loc <> '') and FileExists(AddBackslash(Loc) + DesignerExeName) then
      begin
        Result := RemoveBackslashUnlessRoot(Loc);
        Exit;
      end;
    end;
  end;
end;

// ★ 卸载器不调用 InitializeSetup，两边的全局变量是各算各的 ——
//   所以这个必须幂等，凡是用到它的地方都先兜一道。
procedure EnsureDesignerDir();
begin
  if gDesignerProbed then Exit;
  gDesignerProbed := True;
  gDesignerDir := FindDesignerDir();
  // [Code] 出错只在 /LOG= 里看得到，所以关键判定都记一笔
  if gDesignerDir = '' then
    Log('Node Cut: 注册表里没找到 Substance 3D Designer 的 InstallLocation')
  else
    Log('Node Cut: 检测到 Designer 安装在 ' + gDesignerDir);
end;

function B2S(B: Boolean): String;
begin
  if B then Result := '是' else Result := '否';
end;

function DesignerRunning(): Boolean;
begin
  EnsureDesignerDir();
  if gDesignerDir = '' then
    Result := False        // 找不到 Designer 就判不了，当成没在跑（宁可不拦）
  else
    Result := BusyReason(AddBackslash(gDesignerDir) + DesignerExeName) <> '';
  Log('Node Cut: Designer 正在运行 = ' + B2S(Result));
end;

// 杀完不能就当好了，要轮询等它真的释放。
// 崩溃上报进程同样加载 Designer 的模块，一起结束掉。
function KillDesigner(): Boolean;
var
  R, I: Integer;
begin
  Exec('taskkill.exe',
       '/F /IM "' + DesignerExeName + '" /IM "' + CrashReporterName + '"',
       '', SW_HIDE, ewWaitUntilTerminated, R);

  Result := False;
  for I := 1 to 30 do
  begin
    if not DesignerRunning() then
    begin
      Result := True;
      Exit;
    end;
    Sleep(400);
  end;
end;

function CheckBeforeInstall(): Boolean;
var
  R: Integer;
begin
  Result := True;
  EnsureDesignerDir();

  if gDesignerDir = '' then
  begin
    R := SuppressibleMsgBox(
      '没有检测到 Substance 3D Designer。' + #13#10 + #13#10 +
      '如果你确实已经装了（比如装在非常规位置），可以点「是」继续安装。' + #13#10 +
      '如果还没装，请先装好 Designer 再装本插件。',
      mbConfirmation, MB_YESNO, IDYES);
    Result := (R = IDYES);
    Exit;
  end;

  if not DesignerRunning() then Exit;

  R := SuppressibleMsgBox(
    'Substance 3D Designer 正在运行。' + #13#10 + #13#10 +
    '插件只在 Designer 启动的时候加载一次，所以装完必须重新启动 Designer 才会生效。' + #13#10 + #13#10 +
    '要现在帮你结束 Designer 吗？装完你再自己打开就行。' + #13#10 +
    '⚠ 结束会丢掉没有保存的工程，请先确认已存盘；不想现在关就选「否」，装完自己重启也一样。',
    mbConfirmation, MB_YESNO, IDNO);

  if R = IDYES then
  begin
    if not KillDesigner() then
    begin
      SuppressibleMsgBox('没能结束 Substance 3D Designer，请手动退出后重新运行本安装包。',
                         mbError, MB_OK, IDOK);
      Result := False;
    end;
  end;
end;

function CheckBeforeUninstall(): Boolean;
var
  R: Integer;
begin
  Result := True;
  EnsureDesignerDir();

  if not DesignerRunning() then Exit;

  R := SuppressibleMsgBox(
    'Substance 3D Designer 正在运行，现在卸载会删不干净。' + #13#10 + #13#10 +
    '请先完全退出 Substance 3D Designer 再卸载。' + #13#10 + #13#10 +
    '要现在帮你结束 Designer 吗？' + #13#10 +
    '⚠ 结束会丢掉没有保存的工程，请先确认已存盘。',
    mbConfirmation, MB_YESNO, IDNO);

  if R <> IDYES then
  begin
    Result := False;
    Exit;
  end;

  if not KillDesigner() then
  begin
    SuppressibleMsgBox('没能结束 Substance 3D Designer，请手动退出后重新卸载。',
                       mbError, MB_OK, IDOK);
    Result := False;
  end;
end;

function InitializeSetup(): Boolean;
begin
  EnsureDesignerDir();
  Result := True;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if not CheckBeforeInstall() then
    Result := '安装已取消：Substance 3D Designer 还在运行。';
end;

// 卸载器的入口是 InitializeUninstall，不是 InitializeSetup
function InitializeUninstall(): Boolean;
begin
  if UninstallSilent() then
  begin
    Result := True;      // 静默卸载：尽力删，不弹窗（弹窗会卡死在等人点）
    Exit;
  end;
  Result := CheckBeforeUninstall();
end;

// 把自动检测到的路径摊开给用户看，免得他不知道装到哪去了
procedure CurPageChanged(CurPageID: Integer);
var
  S: String;
begin
  if CurPageID = wpReady then
  begin
    EnsureDesignerDir();
    S := '插件位置：' + ExpandConstant('{app}');
    if gDesignerDir <> '' then
      S := S + #13#10 + 'Designer：' + gDesignerDir;
    S := S + #13#10 + #13#10 + '装完请重新启动 Substance 3D Designer。';
    WizardForm.ReadyMemo.Text := WizardForm.ReadyMemo.Text + #13#10 + #13#10 + S;
  end;
end;
