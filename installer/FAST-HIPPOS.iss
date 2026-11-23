; FAST-HIPPOS: Windows setup (Inno Setup 6). Build with installer\build-windows.ps1, which collects the files in
; installer\build\payload and passes the version.
;
; The setup holds the program and uv. After copying them it runs installer\install.py (through run-install.cmd), which
; downloads Python and the packages. Everything ends up in one folder per user ({localappdata}\FAST-HIPPOS, no
; administrator rights); uninstalling removes that folder. Settings (%USERPROFILE%\.fast_hippos) and results stay.
;
; Cellpose is set up in the program's window, which can offer an installation that is already on the computer.
; Unattended (for example by IT):  FAST-HIPPOS-Setup.exe /VERYSILENT /CELLPOSE=3   (3, 4, 3,4 or none)

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{A8EDC50D-8553-4561-9EB0-0947573A722E}
AppName=FAST-HIPPOS
AppVersion={#AppVersion}
AppPublisher=Netherlands Cancer Institute - Jalink lab
AppPublisherURL=https://github.com/Jalink-lab/FAST-HIPPOS-Python
DefaultDirName={localappdata}\FAST-HIPPOS
DisableProgramGroupPage=yes
DisableDirPage=no
PrivilegesRequired=lowest
OutputDir=build
OutputBaseFilename=FAST-HIPPOS-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=FAST-HIPPOS.ico
WizardImageFile=wizard-large-100.bmp,wizard-large-125.bmp,wizard-large-150.bmp,wizard-large-200.bmp
WizardSmallImageFile=wizard-small-100.bmp,wizard-small-125.bmp,wizard-small-150.bmp,wizard-small-200.bmp
UninstallDisplayIcon={app}\program\installer\FAST-HIPPOS.ico
UninstallDisplayName=FAST-HIPPOS
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Inno Setup 6.7+ enables Windows' RedirectionGuard, and the programs Setup starts inherit it. uv links
; python\cpython-3.12-... to the patch version with a junction made without administrator rights, which
; RedirectionGuard refuses to follow: "untrusted mount point (os error 448)". So it stays off.
RedirectionGuard=no

[Tasks]
Name: "desktopicon"; Description: "Put a shortcut on the desktop"; GroupDescription: "Shortcuts:"

[Files]
Source: "build\payload\*"; DestDir: "{app}\program"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "build\uv.exe"; DestDir: "{app}\bin"; Flags: ignoreversion

[Icons]
Name: "{userprograms}\FAST-HIPPOS"; Filename: "{app}\FAST-HIPPOS.exe"; WorkingDir: "{app}"; IconFilename: "{app}\program\installer\FAST-HIPPOS.ico"; Comment: "FLIM traces and hit identification"
Name: "{userdesktop}\FAST-HIPPOS"; Filename: "{app}\FAST-HIPPOS.exe"; WorkingDir: "{app}"; IconFilename: "{app}\program\installer\FAST-HIPPOS.ico"; Tasks: desktopicon

[UninstallDelete]
; the environments, Python, the download cache and the log were made by install.py, not copied by the setup
Type: filesandordirs; Name: "{app}"

[Run]
Filename: "{app}\FAST-HIPPOS.exe"; Parameters: "--after-update"; Description: "Start FAST-HIPPOS"; Flags: postinstall nowait skipifsilent unchecked


[Code]
const
  EM_SCROLLCARET = $00B7;
var
  LogMemo: TNewMemo;
  ProgressFile: String;
  LinesShown: Integer;
  { an installation that is there already (from the Apps entry the setup wrote) }
  PrevDir, PrevVersion: String;
  ExistPage: TInputOptionWizardPage;
  Removing: Boolean;

{ While the installation runs, Setup waits in its own loop and handles the window's messages itself: a script
  Exec that waits disables the whole wizard (it cannot be moved, scrolled or clicked). Setup is 32-bit. }
type
  TWinMsg = record
    hwnd: Longword;
    message: Longword;
    wParam: Longint;
    lParam: Longint;
    time: Longword;
    ptX: Longint;
    ptY: Longint;
  end;

function PeekMessage(var Msg: TWinMsg; hWnd, MsgFilterMin, MsgFilterMax, RemoveMsg: Longword): Bool;
external 'PeekMessageW@user32.dll stdcall';
function TranslateMessage(var Msg: TWinMsg): Bool;
external 'TranslateMessage@user32.dll stdcall';
function DispatchMessage(var Msg: TWinMsg): Longint;
external 'DispatchMessageW@user32.dll stdcall';

procedure HandleMessages;
var
  Msg: TWinMsg;
begin
  while PeekMessage(Msg, 0, 0, 0, 1) do  { PM_REMOVE }
  begin
    TranslateMessage(Msg);
    DispatchMessage(Msg);
  end;
end;

{ the installation this setup made earlier: where, and which version }
procedure FindPrevious;
var
  Key: String;
begin
  Key := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{A8EDC50D-8553-4561-9EB0-0947573A722E}_is1';
  PrevDir := '';
  PrevVersion := '';
  if RegQueryStringValue(HKCU, Key, 'InstallLocation', PrevDir) then
  begin
    PrevDir := RemoveBackslashUnlessRoot(PrevDir);
    if not FileExists(PrevDir + '\unins000.exe') then PrevDir := '';
  end;
  if PrevDir = '' then Exit;
  RegQueryStringValue(HKCU, Key, 'DisplayVersion', PrevVersion);
end;

procedure InitializeWizard;
var
  Which: String;
begin
  FindPrevious;
  if PrevDir <> '' then
  begin
    if PrevVersion = '{#AppVersion}' then
      Which := 'This version (' + PrevVersion + ') is installed'
    else
      Which := 'FAST-HIPPOS ' + PrevVersion + ' is installed';
    ExistPage := CreateInputOptionPage(wpWelcome, 'FAST-HIPPOS is installed already',
      Which + ' in ' + PrevDir + '.',
      'This setup has version {#AppVersion}. Updating keeps your settings, results and Cellpose. Removing takes ' +
      'FAST-HIPPOS and the Cellpose installed with it off this computer (your settings and results stay).', True, False);
    ExistPage.Add('Update it');
    ExistPage.Add('Remove it');
    ExistPage.SelectedValueIndex := 0;
  end;

  { the installation's messages, shown under the progress bar instead of in a console window }
  LogMemo := TNewMemo.Create(WizardForm);
  LogMemo.Parent := WizardForm.InstallingPage;
  LogMemo.Left := WizardForm.ProgressGauge.Left;
  LogMemo.Width := WizardForm.ProgressGauge.Width;
  LogMemo.Top := WizardForm.ProgressGauge.Top + WizardForm.ProgressGauge.Height + ScaleY(12);
  LogMemo.Height := WizardForm.InstallingPage.Height - LogMemo.Top - ScaleY(4);
  LogMemo.Anchors := [akLeft, akTop, akRight, akBottom];
  LogMemo.ReadOnly := True;
  LogMemo.ScrollBars := ssVertical;
  LogMemo.WordWrap := False;
  LogMemo.Font.Name := 'Consolas';
  LogMemo.Font.Size := 8;
  LogMemo.Visible := False;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := (PageID = wpSelectDir) and (PrevDir <> '');  { an update goes into the folder that is there }
end;

function Quote(S: String): String;
begin
  Result := '"' + S + '"';
end;

function InstallArguments: String;
begin
  Result := '--cellpose ' + ExpandConstant('{param:cellpose|none}');
  if WizardIsTaskSelected('desktopicon') then Result := Result + ' --desktop';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  i: Integer;
begin
  Result := True;
  if (PrevDir <> '') and (CurPageID = ExistPage.ID) and (ExistPage.SelectedValueIndex = 1) then
  begin
    { the uninstaller of that installation; this setup then closes }
    if Exec(PrevDir + '\unins000.exe', '', '', SW_SHOW, ewNoWait, i) then
    begin
      Removing := True;
      WizardForm.Close;
    end
    else
      MsgBox('The uninstaller could not be started: ' + SysErrorMessage(i), mbError, MB_OK);
    Result := False;
  end;
end;

{ install.py writes the progress file: per mille done, the step, the number of messages, the last messages }
procedure ShowProgress;
var
  Lines: TArrayOfString;
  i, Count, New, Last: Integer;
begin
  if not LoadStringsFromFile(ProgressFile, Lines) then Exit;
  Last := GetArrayLength(Lines) - 1;
  if Last < 2 then Exit;
  if StrToIntDef(Lines[0], -1) >= 0 then
    WizardForm.ProgressGauge.Position := 30 + StrToIntDef(Lines[0], 0) * 97 div 100;
  WizardForm.StatusLabel.Caption := Lines[1];
  Count := StrToIntDef(Lines[2], LinesShown);
  New := Count - LinesShown;
  if New > Last - 2 then New := Last - 2;
  if New > 0 then
  begin
    for i := Last - New + 1 to Last do
      LogMemo.Lines.Add(Lines[i]);
    while LogMemo.Lines.Count > 3000 do
      LogMemo.Lines.Delete(0);
    LogMemo.SelStart := Length(LogMemo.Text);
    SendMessage(LogMemo.Handle, EM_SCROLLCARET, 0, 0);
  end;
  LinesShown := Count;
end;

{ the last lines of the installation: from the window, or, when Python did not even start, from the output file }
function LastMessages: String;
var
  Lines: TArrayOfString;
  i, First: Integer;
begin
  Result := '';
  if LogMemo.Lines.Count > 0 then
  begin
    First := LogMemo.Lines.Count - 8;
    if First < 0 then First := 0;
    for i := First to LogMemo.Lines.Count - 1 do
      Result := Result + LogMemo.Lines[i] + #13#10;
  end
  else if LoadStringsFromFile(ExpandConstant('{app}\install-output.log'), Lines) then
  begin
    First := GetArrayLength(Lines) - 8;
    if First < 0 then First := 0;
    for i := First to GetArrayLength(Lines) - 1 do
      Result := Result + Lines[i] + #13#10;
  end;
  if Trim(Result) = '' then Result := '(none)';
end;

{ A FAST-HIPPOS that runs from the installation folder (the program, or its Cellpose processes) keeps its
  files in use, so they cannot be replaced or removed: it is closed first. }
function RunningCount(Dir: String; Stop: Boolean): Integer;
var
  Command: String;
begin
  Command := '$d = ''' + RemoveBackslashUnlessRoot(Dir) + '\''; ' +
    '$p = @(Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and ' +
    '$_.ExecutablePath.StartsWith($d, [StringComparison]::OrdinalIgnoreCase) }); ';
  if Stop then
    Command := Command + '$p | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; ' +
      'Start-Sleep -Seconds 2; ';
  Command := Command + 'exit $p.Count';
  if not Exec('powershell.exe', '-NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "' + Command + '"', '',
              SW_HIDE, ewWaitUntilTerminated, Result) then
    Result := 0;
end;

function CloseRunning(Dir: String; Silent: Boolean): Boolean;
begin
  Result := True;
  if not DirExists(Dir) or (RunningCount(Dir, False) = 0) then Exit;
  if not Silent then
    Result := MsgBox('FAST-HIPPOS is running from ' + Dir + '. Setup closes it first (your results and ' +
                     'settings are kept; its browser tab waits and comes back when FAST-HIPPOS starts again).', mbConfirmation, MB_OKCANCEL) = IDOK;
  if Result then
    RunningCount(Dir, True);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if not CloseRunning(WizardDirValue, WizardSilent) then
    Result := 'FAST-HIPPOS is still running. Close it and run this setup again.';
end;

function InitializeUninstall: Boolean;
begin
  Result := CloseRunning(ExpandConstant('{app}'), UninstallSilent);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Code, Ticks: Integer;
  Script, ExitFile, Text: AnsiString;
begin
  if CurStep = ssPostInstall then
  begin
    ProgressFile := ExpandConstant('{app}\install-progress.txt');
    DeleteFile(ProgressFile);
    LinesShown := 0;
    WizardForm.ProgressGauge.Min := 0;
    WizardForm.ProgressGauge.Max := 1000;
    WizardForm.ProgressGauge.Position := 30;
    WizardForm.FilenameLabel.Caption := '';
    WizardForm.StatusLabel.Caption := 'Downloading Python and the program''s packages...';
    LogMemo.Visible := True;
    Script := ExpandConstant('{app}\program\installer\run-install.cmd');
    { run-install.cmd writes its exit code to install-exit.txt when it is done }
    ExitFile := ExpandConstant('{app}\install-exit.txt');
    DeleteFile(ExitFile);
    Code := -1;
    if Exec(ExpandConstant('{cmd}'), '/c "' + Quote(Script) + ' ' + InstallArguments + ' --progress ' +
            Quote(ProgressFile) + '"', '', SW_HIDE, ewNoWait, Code) then
    begin
      Ticks := 0;
      while not FileExists(ExitFile) do
      begin
        HandleMessages;
        Sleep(40);
        Ticks := Ticks + 1;
        if Ticks mod 12 = 0 then ShowProgress;
        { about once a minute: has the installation stopped without saying so? (nothing of it runs any more) }
        if (Ticks mod 1500 = 0) and not FileExists(ExitFile) and (RunningCount(ExpandConstant('{app}'), False) = 0) then
        begin
          Sleep(2000);
          if not FileExists(ExitFile) then Break;
        end;
      end;
      Sleep(200);
      if LoadStringFromFile(ExitFile, Text) then
        Code := StrToIntDef(Trim(String(Text)), -1);
    end;
    ShowProgress;
    if Code <> 0 then
      MsgBox('The installation did not finish. The last messages:' + #13#10#13#10 + LastMessages + #13#10#13#10 +
             'All messages are in ' + ExpandConstant('{app}\install-output.log') + '. Run this setup again to retry.',
             mbError, MB_OK);
  end;
end;

function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo, MemoTypeInfo, MemoComponentsInfo,
  MemoGroupInfo, MemoTasksInfo: String): String;
begin
  Result := MemoDirInfo + NewLine + NewLine + 'Python and the packages are downloaded (about 0.5 GB). Cellpose can be ' +
    'set up afterwards in the FAST-HIPPOS window.';
  if MemoTasksInfo <> '' then
    Result := Result + NewLine + NewLine + MemoTasksInfo;
end;

procedure CancelButtonClick(CurPageID: Integer; var Cancel, Confirm: Boolean);
begin
  if Removing then Confirm := False;  { closed because the uninstaller took over }
end;
