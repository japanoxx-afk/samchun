using System;
using System.IO;
using System.Diagnostics;
using System.Drawing;
using System.Windows.Forms;
using System.Security.Cryptography;
using System.Reflection;
using System.Threading;
using System.Runtime.InteropServices;

[assembly: AssemblyVersion("1.3.59.0")]
class Launcher : Form {
 static readonly string DefaultGame = Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"3kd2.exe");
 static string Root = AppDomain.CurrentDomain.BaseDirectory;
 TextBox path = new TextBox(); CheckBox window = new CheckBox(); Label status = new Label();
 ComboBox resolution = new ComboBox(); CheckBox stretch = new CheckBox();
 ComboBox video = new ComboBox();
 CheckBox rally = new CheckBox(); TextBox serverIp = new TextBox();
 Label arenaStatus = new Label();
 static readonly string[] Resolutions = {"1280 × 720 (16:9)", "1600 × 900 (16:9)", "1920 × 1080 (16:9)", "2560 × 1440 (16:9)", "3840 × 2160 (16:9)", "1280 × 960 (4:3)"};
 static readonly int[] Widths = {1280,1600,1920,2560,3840,1280}, Heights = {720,900,1080,1440,2160,960};
 [DllImport("kernel32", CharSet=CharSet.Unicode)] static extern bool WritePrivateProfileString(string section,string key,string value,string file);
 [DllImport("kernel32", CharSet=CharSet.Unicode, SetLastError=true)] static extern bool QueryFullProcessImageName(IntPtr process,int flags,System.Text.StringBuilder path,ref int size);
 static string ProcessImagePath(Process process) {var buffer=new System.Text.StringBuilder(32768);int size=buffer.Capacity;if(!QueryFullProcessImageName(process.Handle,0,buffer,ref size))throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());return buffer.ToString();}
 static string Hash(string file) { using(var s=File.OpenRead(file)) using(var h=SHA256.Create()) return BitConverter.ToString(h.ComputeHash(s)).Replace("-",""); }
 static string Quote(string s) { return "\""+s+"\""; }
 static bool Running(string game) { foreach(string name in new[]{Path.GetFileNameWithoutExtension(game),"3kd2-modern","3kd2-record","3kd2-playback","3kd2-replay"})foreach(var p in Process.GetProcessesByName(name)) { try { if(string.Equals(Path.GetDirectoryName(p.MainModule.FileName),Path.GetDirectoryName(game),StringComparison.OrdinalIgnoreCase)) return true; } catch { return true; } } return false; }
 static void Backup(string dir,string name) { string f=Path.Combine(dir,name), b=Path.Combine(dir,"launcher-backup",name); Directory.CreateDirectory(Path.GetDirectoryName(b)); if(File.Exists(f)&&!File.Exists(b)) File.Copy(f,b); }
 void Guard(Action action) { try { action(); } catch(Exception e) {string log=LauncherDiagnostics.Save(e);status.Text="실패: "+e.Message;MessageBox.Show(e.Message+(log==null?"":"\r\n오류 로그: "+log),"작업 실패");} }
 Button Button(string text,int y,Action action) { var b=new Button {Text=text,Left=28,Top=y,Width=584,Height=38}; b.Click+=(s,e)=>Guard(action); Controls.Add(b); return b; }
 public Launcher() {
 Text="삼국지 천명 2 런처 · 1.3.59"; ClientSize=new Size(640,905); Font=new Font("맑은 고딕",10); FormBorderStyle=FormBorderStyle.FixedSingle; MaximizeBox=false;
 Controls.Add(new Label {Text="삼국지 천명 2",Left=28,Top=22,Width=580,Height=40,Font=new Font("맑은 고딕",22,FontStyle.Bold)});
 path.SetBounds(28,78,490,28); path.Text=File.Exists(Path.Combine(Root,"game-path.txt"))?File.ReadAllText(Path.Combine(Root,"game-path.txt")).Trim():DefaultGame; Controls.Add(path);
 var browse=new Button {Text="찾기",Left=526,Top=76,Width=86,Height=30}; browse.Click+=(s,e)=>{using(var d=new OpenFileDialog {Filter="게임|3kd2.exe"}) if(d.ShowDialog()==DialogResult.OK)path.Text=d.FileName;};Controls.Add(browse);
 window.Text="창모드 (cnc-ddraw / 게임 호환성 확인 필요)"; window.SetBounds(28,120,584,30); window.Checked=true;Controls.Add(window);
 Controls.Add(new Label {Text="출력 해상도",Left=28,Top=163,Width=110,Height=28});
 resolution.SetBounds(145,158,275,30);resolution.DropDownStyle=ComboBoxStyle.DropDownList;resolution.Items.AddRange(Resolutions);resolution.SelectedIndex=2;Controls.Add(resolution);
 stretch.Text="16:9 화면 가득 채우기 (가로 늘림)";stretch.SetBounds(28,197,584,28);stretch.Checked=true;Controls.Add(stretch);
 string settingsFile=Path.Combine(Root,"display-settings.txt");if(File.Exists(settingsFile)){string[] values=File.ReadAllLines(settingsFile);int index;bool value;if(values.Length>=3&&int.TryParse(values[0],out index)&&index>=0&&index<Resolutions.Length&&bool.TryParse(values[1],out value)){resolution.SelectedIndex=index;stretch.Checked=value;if(bool.TryParse(values[2],out value))window.Checked=value;}}
 Controls.Add(new Label {Text="화면 출력 크기를 확대합니다. 전장 시야 범위는 원본과 같습니다.\r\n가득 채우기 해제: 원본 화면비를 유지하며 좌우 여백을 표시합니다.",Left=28,Top=231,Width=584,Height=48});
 rally.Text="랠리·자동채집·입력창·F2/일꾼 선택 패치";rally.SetBounds(28,282,584,28);rally.Checked=true;Controls.Add(rally);
 if(File.Exists(settingsFile)){string[] values=File.ReadAllLines(settingsFile);bool value;if(values.Length>=4&&bool.TryParse(values[3],out value))rally.Checked=value;}
 var gameButton=Button("게임 실행",326,()=>{string game=GamePath();if(!File.Exists(game))throw new Exception("게임 파일(3kd2.exe)을 찾을 수 없습니다. 위쪽 '찾기' 버튼으로 게임 위치를 지정하세요.");if(Running(game))throw new Exception("게임이 이미 실행 중입니다.");NetworkPatch.Validate(false,"Player",serverIp.Text.Trim());rally.Checked=true;InstallWindow(game);File.WriteAllText(Path.Combine(Root,"game-path.txt"),game);ReplayEngine.Start(game,null,serverIp.Text.Trim());status.Text="게임 실행 · 싱글/멀티·연속 경기 자동 기록 시험";});gameButton.Width=280;
 var editorButton=new Button {Text="에디터 실행",Left=320,Top=326,Width=292,Height=38};editorButton.Click+=(s,e)=>Guard(()=>{string game=GamePath();var start=EditorLaunch.Prepare(game);Process.Start(start);File.WriteAllText(Path.Combine(Root,"game-path.txt"),game);status.Text=Path.GetFileName(start.FileName).Equals("3kd2Edit-modern.exe",StringComparison.OrdinalIgnoreCase)?"에디터 실행 · 최대화 / 16비트 색상 호환":"에디터 실행 · 기본 호환 모드 (이 버전은 최대화 패치 미적용)";});Controls.Add(editorButton);
 Button("해상도 / 화면모드 설정 적용",373,()=>{InstallWindow(GamePath());status.Text="설정 적용: "+resolution.Text+" · "+(window.Checked?"창모드":"전체화면")+". Alt+Enter로 전환 가능.";});
 Button("기존 그래픽 DLL / 설정 복원",420,()=>{string game=GamePath(),dir=Path.GetDirectoryName(game),backup=Path.Combine(dir,"launcher-backup");if(Running(game))throw new Exception("게임을 종료한 뒤 복원하세요.");if(!File.Exists(Path.Combine(backup,"ddraw.dll")))throw new Exception("복원할 백업이 없습니다.");File.Copy(Path.Combine(backup,"ddraw.dll"),Path.Combine(dir,"ddraw.dll"),true);if(File.Exists(Path.Combine(backup,"ddraw.ini")))File.Copy(Path.Combine(backup,"ddraw.ini"),Path.Combine(dir,"ddraw.ini"),true);else if(File.Exists(Path.Combine(backup,"ini-was-absent")))File.Delete(Path.Combine(dir,"ddraw.ini"));window.Checked=false;rally.Checked=false;status.Text="기존 그래픽 설정 복원 완료. 원본 게임을 직접 실행하면 원복 상태로 실행됩니다.";});
 var updateButton=Button("런처 업데이트",467,ApplyUpdate);updateButton.Width=280;
 var notesButton=new Button {Text="패치노트",Left=320,Top=467,Width=292,Height=38};notesButton.Click+=(s,e)=>Guard(()=>{using(var dialog=CreatePatchNotesWindow())dialog.ShowDialog(this);});Controls.Add(notesButton);
 Controls.Add(new Label {Left=28,Top=519,Width=584,Height=120,Text="랠리: 건물 선택 후 땅 또는 자원 우클릭 → 랠리 지정\r\n기·오어에 우클릭 또는 수동 랠리 지정 → 생산 후 채집.\r\nF2: 전장 군사 선택 / . : 쉬는 일꾼 선택 (최대 64기)\r\n\r\n생산 유닛 초기 마나: 최대치의 65%\r\n마법: 클릭당 한 기씩 순차 시전 / 건물 팔기: C"});
 var replayButton=Button("리플레이 · 시험 기능",640,()=>{InstallWindow(GamePath());using(var dialog=new ReplayWindow(path.Text))dialog.ShowDialog(this);});replayButton.Width=184;
 var errorLogsButton=new Button {Text="오류 폴더 열기",Left=222,Top=640,Width=184,Height=38};errorLogsButton.Click+=(s,e)=>Guard(LauncherDiagnostics.OpenFolder);Controls.Add(errorLogsButton);
 var reportButton=new Button{Text="오류 리포트 ZIP 저장",Left=416,Top=640,Width=196,Height=38};reportButton.Click+=(s,e)=>Guard(()=>{using(var dialog=new SaveFileDialog{Filter="오류 리포트 ZIP|*.zip",FileName="Samchun-ErrorReport-"+DateTime.Now.ToString("yyyy-MM-dd_HH-mm-ss")+".zip",DefaultExt="zip",AddExtension=true,OverwritePrompt=true})if(dialog.ShowDialog(this)==DialogResult.OK){LauncherDiagnostics.ExportZip(dialog.FileName);status.Text="오류 리포트 저장 완료: "+dialog.FileName;}});Controls.Add(reportButton);
 Controls.Add(new Label {Text="인터넷 플레이 · 회원가입 / 로그인 / 대기실은 게임 안에서",Left=28,Top=685,Width=584,Height=28});
 serverIp.SetBounds(28,720,584,28);serverIp.Text="127.0.0.1";Controls.Add(serverIp);
 Controls.Add(new Label {Text="접속할 서버 IPv4 (내 서버: 127.0.0.1 / 다른 PC: 서버 PC의 IP)",Left=28,Top=752,Width=584,Height=25});
 string networkFile=Path.Combine(Root,"network-settings.txt");if(File.Exists(networkFile)){var v=File.ReadAllLines(networkFile);if(v.Length==2){serverIp.Text=v[1];}}
 var hostButton=new Button {Text="인터넷 서버 구동",Left=28,Top=782,Width=280,Height=38};hostButton.Click+=(s,e)=>Guard(StartCompatServer);Controls.Add(hostButton);
 var joinButton=new Button {Text="입력한 서버로 게임 접속",Left=320,Top=782,Width=292,Height=38};joinButton.Click+=(s,e)=>Guard(LaunchCompat);Controls.Add(joinButton);
 // Replay upload to RTS ARENA is always on (1.3.59): only 2+ player internet matches are sent.
 var arenaButton=new Button{Text="전적 사이트 열기",Left=432,Top=898,Width=180,Height=34};arenaButton.Click+=(s,e)=>Guard(()=>Process.Start(ArenaUpload.DefaultSite+"/samchun/matches"));Controls.Add(arenaButton);
 Controls.Add(new Label{Text="인터넷 대전(사람 2명 이상) 리플레이는 전적 사이트에 자동으로 올라갑니다.",Left=28,Top=902,Width=400,Height=28});
 arenaStatus.SetBounds(28,934,584,24);arenaStatus.ForeColor=Color.DimGray;Controls.Add(arenaStatus);
 ArenaUpload.StatusChanged+=text=>{if(IsHandleCreated&&!IsDisposed)try{BeginInvoke((Action)(()=>arenaStatus.Text=text));}catch(InvalidOperationException){}};
 ArenaUpload.Start(()=>ArenaUpload.ReplayFolder(path.Text),ArenaUpload.DefaultSite);arenaStatus.Text="리플레이 자동 업로드 · 대전 리플레이를 기다리는 중";
 status.SetBounds(28,837,584,60);status.Text="준비 완료 · 원본 EXE 보존, 패치 실행 파일은 별도로 생성합니다.";Controls.Add(status);
 foreach(Control control in Controls)if(control.Top>=231)control.Top+=44;
 Controls.Add(new Label{Text="게임 비디오 모드",Left=28,Top=234,Width=145,Height=28});
 video.SetBounds(175,230,330,30);video.DropDownStyle=ComboBoxStyle.DropDownList;video.Items.AddRange(VideoMode.Names);video.SelectedIndex=VideoMode.Read(path.Text);Controls.Add(video);
 video.SelectedIndexChanged+=delegate{if(video.SelectedIndex==1||video.SelectedIndex==2)status.Text="Direct3D·Voodoo 호환 드라이버로 선택한 모드를 적용합니다. 창모드 설정을 지원하며 실제 적용 모드를 확인합니다.";};
 path.TextChanged+=delegate{video.SelectedIndex=VideoMode.Read(path.Text);};
 AutoScroll=true;AutoScrollMinSize=new Size(640,1010);ClientSize=new Size(640,Math.Min(1010,Math.Max(500,Screen.PrimaryScreen.WorkingArea.Height-60)));
 Shown+=delegate{ApplyUpdate(true);};
 string videoReport=Path.Combine(LauncherDiagnostics.Folder,"video-last.json");DateTime lastVideo=File.Exists(videoReport)?File.GetLastWriteTimeUtc(videoReport):DateTime.MinValue;
 var videoTimer=new System.Windows.Forms.Timer{Interval=1000};videoTimer.Tick+=delegate{try{if(!File.Exists(videoReport)||File.GetLastWriteTimeUtc(videoReport)==lastVideo)return;var report=new System.Web.Script.Serialization.JavaScriptSerializer().Deserialize<System.Collections.Generic.Dictionary<string,object>>(File.ReadAllText(videoReport));lastVideo=File.GetLastWriteTimeUtc(videoReport);status.Text=(report.ContainsKey("failed")&&Convert.ToBoolean(report["failed"])?"비디오 초기화 실패 · 오류 리포트 ZIP을 저장해 주세요. ":"비디오 모드 · ")+"요청: "+Convert.ToString(report["requested"])+" / 실제 적용: "+Convert.ToString(report["actual"])+(Convert.ToBoolean(report["fallback"])?" · 요청 모드 초기화 실패. 오류 리포트 ZIP으로 상세 정보를 저장할 수 있습니다.":"");}catch(IOException){}catch(ArgumentException){} };videoTimer.Start();FormClosed+=delegate{videoTimer.Dispose();if(updateTimer!=null)updateTimer.Dispose();};
 }
 internal static Form CreatePatchNotesWindow() {
 string notes;
 using(var stream=Assembly.GetExecutingAssembly().GetManifestResourceStream("PATCH_NOTES.txt")) {
 if(stream==null)throw new InvalidDataException("패치노트가 없습니다. 런처를 다시 업데이트하세요.");
 using(var reader=new StreamReader(stream,System.Text.Encoding.UTF8))notes=reader.ReadToEnd();
 }
 notes=notes.Replace("\r\n","\n").Replace("\r","\n");
 var dialog=new Form {Text="삼국지 천명 2 · 패치노트",ClientSize=new Size(780,720),MinimumSize=new Size(560,420),StartPosition=FormStartPosition.CenterParent,Font=new Font("맑은 고딕",10),MinimizeBox=false,MaximizeBox=true};
 var content=new RichTextBox {ReadOnly=true,ScrollBars=RichTextBoxScrollBars.Vertical,WordWrap=true,Dock=DockStyle.Fill,BackColor=SystemColors.Window,BorderStyle=BorderStyle.None,DetectUrls=false};
 var bodyFont=new Font("맑은 고딕",10.5f);
 var headingFont=new Font("맑은 고딕",12,FontStyle.Bold);
 content.Font=bodyFont;
 foreach(string line in notes.Split('\n')) {
 content.SelectionFont=(line.StartsWith("v1.")||line=="삼국지 천명 2 런처 패치노트")?headingFont:bodyFont;
 content.SelectionColor=line.StartsWith("v1.")?Color.FromArgb(28,75,125):Color.FromArgb(40,40,40);
 content.AppendText(line+Environment.NewLine);
 }
 content.Select(0,0);content.ScrollToCaret();
 var inset=new Panel {Dock=DockStyle.Fill,Padding=new Padding(20,16,20,12),BackColor=SystemColors.Window};
 inset.Controls.Add(content);
 var close=new Button {Text="닫기",Dock=DockStyle.Bottom,Height=40,DialogResult=DialogResult.Cancel};
 dialog.Controls.Add(inset);dialog.Controls.Add(close);dialog.CancelButton=close;
 return dialog;
 }
 void StartCompatServer() {
 string exe=InstallServer(),expected=Hash(exe);var processes=Process.GetProcessesByName("samchun-server");
 try {
 bool outdated=false;
 foreach(var process in processes) {
 string running;
 try {running=ProcessImagePath(process);}catch {throw new Exception("실행 중인 서버 버전을 확인할 수 없습니다. 기존 서버를 종료한 뒤 다시 구동하세요.");}
 if(!File.Exists(running)||Hash(running)!=expected)outdated=true;
 }
 if(processes.Length>0&&!outdated){status.Text="최신 인터넷 서버가 실행 중입니다. 계정 전적 저장을 지원합니다.";return;}
 if(outdated) {
 foreach(var connection in System.Net.NetworkInformation.IPGlobalProperties.GetIPGlobalProperties().GetActiveTcpConnections())
 if((connection.LocalEndPoint.Port==4800||connection.LocalEndPoint.Port==4901)&&connection.State==System.Net.NetworkInformation.TcpState.Established)
 throw new Exception("구형 서버에 접속자가 있습니다. 모두 게임에서 로그아웃한 뒤 서버 구동을 다시 누르세요. 기존 계정은 유지됩니다.");
 foreach(var process in processes) {try {if(!process.HasExited)process.Kill();}catch(InvalidOperationException){}}
 foreach(var process in processes) {try {if(!process.WaitForExit(5000))throw new Exception("구형 서버 종료 대기시간 초과");}catch(InvalidOperationException){}}
 }
 Process.Start(new ProcessStartInfo(exe){WorkingDirectory=Path.GetDirectoryName(exe),UseShellExecute=true,WindowStyle=ProcessWindowStyle.Hidden});
 status.Text=outdated?"구형 서버를 최신 서버로 전환했습니다. 기존 계정 유지 · 계정 전적 저장 지원.":"인터넷 서버 실행 요청 · 계정 전적 저장 지원. 입력한 서버로 게임 접속을 누르세요.";
 }finally {foreach(var process in processes)process.Dispose();}
 }
 void LaunchCompat() {
 string game=GamePath(),ip=serverIp.Text.Trim();
 NetworkPatch.Validate(false,"Player",ip);
 if(Running(game))throw new Exception("게임을 종료한 뒤 실행하세요.");
 rally.Checked=true;InstallWindow(game);
 File.WriteAllText(Path.Combine(Root,"game-path.txt"),game);
 File.WriteAllLines(Path.Combine(Root,"network-settings.txt"),new[]{"Player",ip});
 ReplayEngine.Start(game,null,ip);
 status.Text="멀티 기록 시험 · 참가자 모두 같은 런처 필요. INTERNET → 회원가입/로그인 → 대기실. 서버: "+ip;
 }
 internal static string InstallServer() {
 string dir=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"SamchunServer","bin",Assembly.GetExecutingAssembly().GetName().Version.ToString());
 Directory.CreateDirectory(dir);string exe=Path.Combine(dir,"samchun-server.exe");
 using(var stream=Assembly.GetExecutingAssembly().GetManifestResourceStream("samchun-server.exe")) {
 if(stream==null)throw new InvalidDataException("내장 서버 파일이 없습니다. 런처 업데이트를 다시 실행하세요.");
 byte[] data;using(var memory=new MemoryStream()){stream.CopyTo(memory);data=memory.ToArray();}
 string expected;using(var sha=SHA256.Create())expected=BitConverter.ToString(sha.ComputeHash(data)).Replace("-","");
 if(File.Exists(exe)&&Hash(exe)==expected)return exe;
 string temporary=exe+"."+Guid.NewGuid().ToString("N")+".tmp";
 try{File.WriteAllBytes(temporary,data);if(Hash(temporary)!=expected)throw new InvalidDataException("내장 서버 검증 실패");if(File.Exists(exe))File.Replace(temporary,exe,null);else File.Move(temporary,exe);}finally{if(File.Exists(temporary))File.Delete(temporary);}
 }return exe;
 }
 // Game executable from the path box. When it is missing (for example a launcher downloaded to
 // another folder), look next to the launcher and ask the user to pick 3kd2.exe once.
 string GamePath() {
  string current=path.Text.Trim().Trim('"');
  try{if(current.Length>0&&File.Exists(Path.GetFullPath(current)))return Path.GetFullPath(current);}catch(ArgumentException){}catch(NotSupportedException){}
  foreach(string guess in new[]{Path.Combine(Root,"3kd2.exe"),Path.Combine(Root,"..","3kd2.exe")})
   if(File.Exists(guess)){path.Text=Path.GetFullPath(guess);SaveGamePath();return path.Text;}
  MessageBox.Show(this,"게임 실행 파일(3kd2.exe)을 찾을 수 없습니다.\r\n\r\n다음 창에서 삼국지 천명 2가 설치된 폴더의 3kd2.exe 를 선택하세요.\r\n한 번 선택하면 런처가 기억합니다.","게임 위치 지정",MessageBoxButtons.OK,MessageBoxIcon.Information);
  using(var d=new OpenFileDialog{Title="삼국지 천명 2 게임 파일(3kd2.exe) 선택",Filter="삼국지 천명 2|3kd2.exe|실행 파일|*.exe",CheckFileExists=true}) {
   if(d.ShowDialog(this)!=DialogResult.OK)throw new Exception("게임 위치(3kd2.exe)를 지정해야 실행할 수 있습니다. 위쪽 '찾기' 버튼으로 지정하세요.");
   path.Text=d.FileName;
  }
  SaveGamePath();return path.Text;
 }
 void SaveGamePath(){try{File.WriteAllText(Path.Combine(Root,"game-path.txt"),path.Text);}catch(IOException){}catch(UnauthorizedAccessException){}}
 void InstallWindow(string game) {
 if(!File.Exists(game))throw new Exception("게임 파일(3kd2.exe)을 찾을 수 없습니다. 위쪽 '찾기' 버튼으로 게임 위치를 지정하세요."); if(Running(game))throw new Exception("게임을 종료한 뒤 설정하세요.");
 VideoMode.Save(game,video.SelectedIndex);
 string graphics=GraphicsRuntime.Prepare();string dir=Path.GetDirectoryName(game),dll=Path.Combine(graphics,"ddraw.dll");Backup(dir,"ddraw.dll");Backup(dir,"ddraw.ini");string backup=Path.Combine(dir,"launcher-backup");if(!File.Exists(Path.Combine(dir,"ddraw.ini"))&&!File.Exists(Path.Combine(backup,"ddraw.ini")))File.WriteAllText(Path.Combine(backup,"ini-was-absent"),"");
 File.Copy(dll,Path.Combine(dir,"ddraw.dll"),true);string ini=Path.Combine(dir,"ddraw.ini");if(!File.Exists(ini))File.Copy(Path.Combine(graphics,"ddraw.ini"),ini);
 ConfigureDisplay(ini,resolution.SelectedIndex,stretch.Checked,window.Checked);
 File.WriteAllLines(Path.Combine(Root,"display-settings.txt"),new[]{resolution.SelectedIndex.ToString(),stretch.Checked.ToString(),window.Checked.ToString(),rally.Checked.ToString()});
 }
 static void ConfigureDisplay(string ini,int index,bool fill,bool windowed) {
 if(index<0||index>=Widths.Length)throw new ArgumentOutOfRangeException("index");
 foreach(string section in new[]{"ddraw","3kd2","3kd2.exe","3kd2-modern","3kd2-modern.exe"})foreach(string[] setting in new[]{new[]{"windowed",windowed?"true":"false"},new[]{"fullscreen","false"},new[]{"width",Widths[index].ToString()},new[]{"height",Heights[index].ToString()},new[]{"maintas",fill?"false":"true"},new[]{"aspect_ratio",""},new[]{"boxing","false"},new[]{"border","true"},new[]{"renderer","auto"},new[]{"shader",""},new[]{"savesettings","0"},new[]{"adjmouse","true"}})if(!WritePrivateProfileString(section,setting[0],setting[1],ini))throw new Exception("ddraw.ini 설정 저장 실패");
 }
 bool updating;
 void ApplyUpdate(){ApplyUpdate(false);}
 string pendingUpdate;System.Windows.Forms.Timer updateTimer,updateRetryTimer;int automaticUpdateFailures;
 bool UpdateCanApply(){if(OwnedForms.Length>0)return false;try{return !Running(Path.GetFullPath(path.Text));}catch(ArgumentException){return true;}catch(NotSupportedException){return true;}}
 void ApplyUpdate(bool automatic) {
 if(updating||pendingUpdate!=null)return;if(updateRetryTimer!=null)updateRetryTimer.Stop();updating=true;status.Text="GitHub에서 최신 패치 버전을 확인하고 있습니다…";
 var worker=new System.ComponentModel.BackgroundWorker();
 worker.WorkerReportsProgress=true;worker.ProgressChanged+=(sender,e)=>{if(!IsDisposed)status.Text=(string)e.UserState;};
 worker.DoWork+=(sender,e)=>{e.Result=OnlineUpdate.DownloadWithProgress(Assembly.GetExecutingAssembly().GetName().Version,message=>worker.ReportProgress(0,message));};
 worker.RunWorkerCompleted+=(sender,e)=>{updating=false;worker.Dispose();if(IsDisposed)return;Guard(()=>{
 if(e.Error!=null){if(automatic){LauncherDiagnostics.Save(e.Error);automaticUpdateFailures++;if(automaticUpdateFailures<3){status.Text="업데이트 연결 실패 · 15초 후 자동으로 다시 확인합니다.";if(updateRetryTimer==null){updateRetryTimer=new System.Windows.Forms.Timer{Interval=15000};updateRetryTimer.Tick+=delegate{updateRetryTimer.Stop();if(!IsDisposed)ApplyUpdate(true);};FormClosed+=delegate{updateRetryTimer.Dispose();};}updateRetryTimer.Start();}else status.Text="자동 업데이트 확인 실패 · 오류 로그를 저장했습니다. 업데이트 버튼으로 다시 확인할 수 있습니다.";return;}throw new Exception("온라인 업데이트 실패: "+e.Error.Message);}
 string source=e.Result as string;if(source==null){status.Text="최신 버전입니다. (GitHub 확인 완료)";return;}
 pendingUpdate=source;
 if(!UpdateCanApply()){status.Text="새 업데이트 준비 완료 · 게임과 열린 창을 닫으면 자동 적용합니다.";if(updateTimer==null){updateTimer=new System.Windows.Forms.Timer{Interval=3000};updateTimer.Tick+=delegate{if(IsDisposed)return;Guard(()=>{if(UpdateCanApply()){updateTimer.Stop();ApplyDownloaded();}});};updateTimer.Start();}return;}
 ApplyDownloaded();
 });};worker.RunWorkerAsync();
 }
 void ApplyDownloaded(){
 string source=pendingUpdate;if(source==null)return;
 // Preserve the current launcher choices across the replacement/restart.
 File.WriteAllText(Path.Combine(Root,"game-path.txt"),path.Text);
 File.WriteAllLines(Path.Combine(Root,"display-settings.txt"),new[]{resolution.SelectedIndex.ToString(),stretch.Checked.ToString(),window.Checked.ToString(),rally.Checked.ToString()});
 File.WriteAllLines(Path.Combine(Root,"network-settings.txt"),new[]{"Player",serverIp.Text.Trim()});
 string helper=Path.Combine(Path.GetDirectoryName(source),"helper.exe");File.Copy(Application.ExecutablePath,helper);
 Process.Start(new ProcessStartInfo(helper,"--apply "+Process.GetCurrentProcess().Id+" "+Quote(Application.ExecutablePath)+" "+Quote(source)){UseShellExecute=false,CreateNoWindow=true});Application.Exit();
 }
 [STAThread] static int Main(string[] args) {
 if(args.Length==3&&args[0]=="--patch-replay-network") {try {CompatPatch.Apply(args[1],args[2]);return 0;}catch(Exception e){Console.WriteLine(e.Message);return 1;}}
 if(args.Length==4&&args[0]=="--build-compat") {try {GamePatches.Build(args[1],args[2]);CompatPatch.Apply(args[2],args[3]);return 0;}catch(Exception e){Console.WriteLine(e.Message);return 1;}}
 if(args.Length==2&&args[0]=="--prepare") {try {using(var form=new Launcher()){string game=Path.GetFullPath(args[1]);if(Running(game))throw new Exception("게임이 실행 중입니다.");if(form.rally.Checked)GamePatches.Build(game,Path.Combine(Path.GetDirectoryName(game),"3kd2-modern.exe"));form.InstallWindow(game);Console.WriteLine("Game patch and display settings prepared.");return 0;}}catch(Exception e){Console.WriteLine(e.Message);return 1;}}
 if(args.Length==3&&args[0]=="--build-game") {try {Console.WriteLine(GamePatches.Build(args[1],args[2]));return 0;}catch(Exception e){Console.WriteLine(e.Message);return 1;}}
 if(args.Length==4&&args[0]=="--apply") {string target=args[2],source=args[3];try { try {if(!Process.GetProcessById(int.Parse(args[1])).WaitForExit(15000))throw new Exception("기존 런처 종료 대기시간 초과");}catch(ArgumentException){} if(!string.Equals(Hash(source),File.ReadAllText(Path.Combine(Path.GetDirectoryName(source),"SHA256.txt")).Trim(),StringComparison.OrdinalIgnoreCase))throw new Exception("SHA256 불일치");File.Copy(target,target+".bak",true);try {File.Copy(source,target,true);}catch {File.Copy(target+".bak",target,true);throw;}Process.Start(target);return 0;}catch(Exception e){MessageBox.Show("업데이트 실패: "+e.Message);return 1;} }
 if((args.Length==2||args.Length==3)&&args[0]=="--arena-upload") {try {foreach(string line in ArenaUpload.Scan(args[1],args.Length==3?args[2]:ArenaUpload.DefaultSite,ArenaSecret.Token,DateTime.UtcNow))Console.WriteLine(line);return 0;}catch(Exception e){Console.WriteLine(e.Message);return 1;}}
 if(args.Length==1&&args[0]=="--self-test") {Console.WriteLine("Version="+Assembly.GetExecutingAssembly().GetName().Version+"; Game="+File.Exists(DefaultGame)+"; Runtime="+File.Exists(Path.Combine(Root,@"runtime\cnc-ddraw\ddraw.dll"))+"; SHA256="+Hash(Application.ExecutablePath));return File.Exists(DefaultGame)&&File.Exists(Path.Combine(Root,@"runtime\cnc-ddraw\ddraw.dll"))?0:1;}
 Application.SetUnhandledExceptionMode(UnhandledExceptionMode.CatchException);Application.ThreadException+=(s,e)=>{string log=LauncherDiagnostics.Save(e.Exception);MessageBox.Show("런처 오류: "+e.Exception.Message+(log==null?"":"\r\n오류 로그: "+log),"런처 오류");};AppDomain.CurrentDomain.UnhandledException+=(s,e)=>LauncherDiagnostics.Save(e.ExceptionObject as Exception ?? new Exception("Unknown launcher exception"));
 Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);Application.Run(new Launcher());return 0;
 }
}
