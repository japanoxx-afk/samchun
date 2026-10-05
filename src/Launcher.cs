using System;
using System.IO;
using System.Diagnostics;
using System.Drawing;
using System.Windows.Forms;
using System.Security.Cryptography;
using System.Reflection;
using System.Threading;
using System.Runtime.InteropServices;

[assembly: AssemblyVersion("1.3.16.0")]
class Launcher : Form {
 static readonly string DefaultGame = Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"3kd2.exe");
 static string Root = AppDomain.CurrentDomain.BaseDirectory;
 TextBox path = new TextBox(); CheckBox window = new CheckBox(); Label status = new Label();
 ComboBox resolution = new ComboBox(); CheckBox stretch = new CheckBox();
 CheckBox rally = new CheckBox(); TextBox serverIp = new TextBox();
 static readonly string[] Resolutions = {"1280 × 720 (16:9)", "1600 × 900 (16:9)", "1920 × 1080 (16:9)", "2560 × 1440 (16:9)", "3840 × 2160 (16:9)", "1280 × 960 (4:3)"};
 static readonly int[] Widths = {1280,1600,1920,2560,3840,1280}, Heights = {720,900,1080,1440,2160,960};
 [DllImport("kernel32", CharSet=CharSet.Unicode)] static extern bool WritePrivateProfileString(string section,string key,string value,string file);
 [DllImport("kernel32", CharSet=CharSet.Unicode, SetLastError=true)] static extern bool QueryFullProcessImageName(IntPtr process,int flags,System.Text.StringBuilder path,ref int size);
 static string ProcessImagePath(Process process) {var buffer=new System.Text.StringBuilder(32768);int size=buffer.Capacity;if(!QueryFullProcessImageName(process.Handle,0,buffer,ref size))throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());return buffer.ToString();}
 static string Hash(string file) { using(var s=File.OpenRead(file)) using(var h=SHA256.Create()) return BitConverter.ToString(h.ComputeHash(s)).Replace("-",""); }
 static string Quote(string s) { return "\""+s+"\""; }
 static bool Running(string game) { foreach(string name in new[]{Path.GetFileNameWithoutExtension(game),"3kd2-modern"})foreach(var p in Process.GetProcessesByName(name)) { try { if(string.Equals(Path.GetDirectoryName(p.MainModule.FileName),Path.GetDirectoryName(game),StringComparison.OrdinalIgnoreCase)) return true; } catch { return true; } } return false; }
 static void Backup(string dir,string name) { string f=Path.Combine(dir,name), b=Path.Combine(dir,"launcher-backup",name); Directory.CreateDirectory(Path.GetDirectoryName(b)); if(File.Exists(f)&&!File.Exists(b)) File.Copy(f,b); }
 void Guard(Action action) { try { action(); } catch(Exception e) { status.Text="실패: "+e.Message; MessageBox.Show(e.Message,"작업 실패"); } }
 Button Button(string text,int y,Action action) { var b=new Button {Text=text,Left=28,Top=y,Width=584,Height=38}; b.Click+=(s,e)=>Guard(action); Controls.Add(b); return b; }
 public Launcher() {
 Text="삼국지 천명 2 런처 · 1.3.16"; ClientSize=new Size(640,905); Font=new Font("맑은 고딕",10); FormBorderStyle=FormBorderStyle.FixedSingle; MaximizeBox=false;
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
 var gameButton=Button("게임 실행",326,()=>{string game=Path.GetFullPath(path.Text); if(!File.Exists(game))throw new Exception("게임 파일을 찾을 수 없습니다."); if(Running(game))throw new Exception("게임이 이미 실행 중입니다."); string launch=rally.Checked?GamePatches.Build(game,Path.Combine(Path.GetDirectoryName(game),"3kd2-modern.exe")):game; if(rally.Checked)CompatPatch.Apply(launch,serverIp.Text.Trim()); InstallWindow(game); File.WriteAllText(Path.Combine(Root,"game-path.txt"),game); Process.Start(new ProcessStartInfo(launch){WorkingDirectory=Path.GetDirectoryName(game),UseShellExecute=true}); status.Text="게임 실행 요청 · "+(rally.Checked?"랠리 패치 사용":"원본 게임");});gameButton.Width=280;
 var editorButton=new Button {Text="에디터 실행",Left=320,Top=326,Width=292,Height=38};editorButton.Click+=(s,e)=>Guard(()=>{string game=Path.GetFullPath(path.Text);var start=EditorLaunch.Prepare(game);Process.Start(start);File.WriteAllText(Path.Combine(Root,"game-path.txt"),game);status.Text=Path.GetFileName(start.FileName).Equals("3kd2Edit-modern.exe",StringComparison.OrdinalIgnoreCase)?"에디터 실행 · 최대화 / 16비트 색상 호환":"에디터 실행 · 기본 호환 모드 (이 버전은 최대화 패치 미적용)";});Controls.Add(editorButton);
 Button("해상도 / 화면모드 설정 적용",373,()=>{InstallWindow(Path.GetFullPath(path.Text));status.Text="설정 적용: "+resolution.Text+" · "+(window.Checked?"창모드":"전체화면")+". Alt+Enter로 전환 가능.";});
 Button("기존 그래픽 DLL / 설정 복원",420,()=>{string game=Path.GetFullPath(path.Text),dir=Path.GetDirectoryName(game),backup=Path.Combine(dir,"launcher-backup");if(Running(game))throw new Exception("게임을 종료한 뒤 복원하세요.");if(!File.Exists(Path.Combine(backup,"ddraw.dll")))throw new Exception("복원할 백업이 없습니다.");File.Copy(Path.Combine(backup,"ddraw.dll"),Path.Combine(dir,"ddraw.dll"),true);if(File.Exists(Path.Combine(backup,"ddraw.ini")))File.Copy(Path.Combine(backup,"ddraw.ini"),Path.Combine(dir,"ddraw.ini"),true);else if(File.Exists(Path.Combine(backup,"ini-was-absent")))File.Delete(Path.Combine(dir,"ddraw.ini"));window.Checked=false;rally.Checked=false;status.Text="기존 그래픽 설정 복원 완료. 원본 게임을 직접 실행하면 원복 상태로 실행됩니다.";});
 var updateButton=Button("런처 업데이트",467,ApplyUpdate);updateButton.Width=280;
 var notesButton=new Button {Text="패치노트",Left=320,Top=467,Width=292,Height=38};notesButton.Click+=(s,e)=>Guard(()=>{using(var dialog=CreatePatchNotesWindow())dialog.ShowDialog(this);});Controls.Add(notesButton);
 Controls.Add(new Label {Left=28,Top=519,Width=584,Height=155,Text="랠리: 건물 선택 후 땅 또는 자원 우클릭 → 랠리 지정\r\n기·오어에 우클릭 또는 수동 랠리 지정 → 생산 후 채집.\r\nF2: 전장 군사 선택 / . : 쉬는 일꾼 선택 (최대 64기)\r\n\r\n생산 유닛 초기 마나: 최대치의 65%\r\n마법: 클릭당 한 기씩 순차 시전"});
 Controls.Add(new Label {Text="인터넷 플레이 · 회원가입 / 로그인 / 대기실은 게임 안에서",Left=28,Top=685,Width=584,Height=28});
 serverIp.SetBounds(28,720,584,28);serverIp.Text="127.0.0.1";Controls.Add(serverIp);
 Controls.Add(new Label {Text="접속할 서버 IPv4 (내 서버: 127.0.0.1 / 다른 PC: 서버 PC의 IP)",Left=28,Top=752,Width=584,Height=25});
 string networkFile=Path.Combine(Root,"network-settings.txt");if(File.Exists(networkFile)){var v=File.ReadAllLines(networkFile);if(v.Length==2){serverIp.Text=v[1];}}
 var hostButton=new Button {Text="인터넷 서버 구동",Left=28,Top=782,Width=280,Height=38};hostButton.Click+=(s,e)=>Guard(StartCompatServer);Controls.Add(hostButton);
 var joinButton=new Button {Text="입력한 서버로 게임 접속",Left=320,Top=782,Width=292,Height=38};joinButton.Click+=(s,e)=>Guard(LaunchCompat);Controls.Add(joinButton);
 status.SetBounds(28,837,584,60);status.Text="준비 완료 · 원본 EXE 보존, 패치 실행 파일은 별도로 생성합니다.";Controls.Add(status);
 }
 internal static Form CreatePatchNotesWindow() {
 string notes;
 using(var stream=Assembly.GetExecutingAssembly().GetManifestResourceStream("PATCH_NOTES.txt")) {
 if(stream==null)throw new InvalidDataException("패치노트가 없습니다. 런처를 다시 업데이트하세요.");
 using(var reader=new StreamReader(stream,System.Text.Encoding.UTF8))notes=reader.ReadToEnd();
 }
 var dialog=new Form {Text="삼국지 천명 2 · 패치노트",ClientSize=new Size(660,620),MinimumSize=new Size(500,400),StartPosition=FormStartPosition.CenterParent,Font=new Font("맑은 고딕",10),MinimizeBox=false,MaximizeBox=true};
 var content=new TextBox {Multiline=true,ReadOnly=true,ScrollBars=ScrollBars.Vertical,WordWrap=true,Dock=DockStyle.Fill,BackColor=SystemColors.Window,Text=notes};
 var close=new Button {Text="닫기",Dock=DockStyle.Bottom,Height=40,DialogResult=DialogResult.Cancel};
 dialog.Controls.Add(content);dialog.Controls.Add(close);dialog.CancelButton=close;
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
 string game=Path.GetFullPath(path.Text),ip=serverIp.Text.Trim();
 NetworkPatch.Validate(false,"Player",ip);
 if(Running(game))throw new Exception("게임을 종료한 뒤 실행하세요.");
 string launch=GamePatches.Build(game,Path.Combine(Path.GetDirectoryName(game),"3kd2-modern.exe"));
 CompatPatch.Apply(launch,ip);InstallWindow(game);
 File.WriteAllText(Path.Combine(Root,"game-path.txt"),game);
 File.WriteAllLines(Path.Combine(Root,"network-settings.txt"),new[]{"Player",ip});
 Process.Start(new ProcessStartInfo(launch){WorkingDirectory=Path.GetDirectoryName(game),UseShellExecute=true});
 status.Text="게임의 INTERNET → 회원가입/로그인 → 대기실. 서버: "+ip;
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
 void InstallWindow(string game) {
 if(!File.Exists(game))throw new Exception("게임 파일을 찾을 수 없습니다."); if(Running(game))throw new Exception("게임을 종료한 뒤 설정하세요.");
 string dir=Path.GetDirectoryName(game),dll=Path.Combine(Root,@"runtime\cnc-ddraw\ddraw.dll");if(!File.Exists(dll))throw new Exception("동봉된 cnc-ddraw DLL이 없습니다.");Backup(dir,"ddraw.dll");Backup(dir,"ddraw.ini");string backup=Path.Combine(dir,"launcher-backup");if(!File.Exists(Path.Combine(dir,"ddraw.ini"))&&!File.Exists(Path.Combine(backup,"ddraw.ini")))File.WriteAllText(Path.Combine(backup,"ini-was-absent"),"");
 File.Copy(dll,Path.Combine(dir,"ddraw.dll"),true);string ini=Path.Combine(dir,"ddraw.ini");if(!File.Exists(ini))File.Copy(Path.Combine(Root,@"runtime\cnc-ddraw\ddraw.ini"),ini);
 ConfigureDisplay(ini,resolution.SelectedIndex,stretch.Checked,window.Checked);
 File.WriteAllLines(Path.Combine(Root,"display-settings.txt"),new[]{resolution.SelectedIndex.ToString(),stretch.Checked.ToString(),window.Checked.ToString(),rally.Checked.ToString()});
 }
 static void ConfigureDisplay(string ini,int index,bool fill,bool windowed) {
 if(index<0||index>=Widths.Length)throw new ArgumentOutOfRangeException("index");
 foreach(string section in new[]{"ddraw","3kd2","3kd2.exe","3kd2-modern","3kd2-modern.exe"})foreach(string[] setting in new[]{new[]{"windowed",windowed?"true":"false"},new[]{"fullscreen","false"},new[]{"width",Widths[index].ToString()},new[]{"height",Heights[index].ToString()},new[]{"maintas",fill?"false":"true"},new[]{"aspect_ratio",""},new[]{"boxing","false"},new[]{"border","true"},new[]{"renderer","auto"},new[]{"shader",""},new[]{"savesettings","0"},new[]{"adjmouse","true"}})if(!WritePrivateProfileString(section,setting[0],setting[1],ini))throw new Exception("ddraw.ini 설정 저장 실패");
 }
 bool updating;
 void ApplyUpdate() {
 if(updating)return;updating=true;status.Text="GitHub에서 새 버전을 확인하고 있습니다…";
 var worker=new System.ComponentModel.BackgroundWorker();
 worker.DoWork+=(sender,e)=>{e.Result=OnlineUpdate.Download(Assembly.GetExecutingAssembly().GetName().Version);};
 worker.RunWorkerCompleted+=(sender,e)=>{updating=false;worker.Dispose();if(IsDisposed)return;Guard(()=>{
 if(e.Error!=null)throw new Exception("온라인 업데이트 실패: "+e.Error.Message);
 string source=e.Result as string;if(source==null){status.Text="최신 버전입니다. (GitHub 확인 완료)";return;}
 string helper=Path.Combine(Path.GetDirectoryName(source),"helper.exe");File.Copy(Application.ExecutablePath,helper);
 Process.Start(new ProcessStartInfo(helper,"--apply "+Process.GetCurrentProcess().Id+" "+Quote(Application.ExecutablePath)+" "+Quote(source)){UseShellExecute=false});Application.Exit();
 });};worker.RunWorkerAsync();
 }
 [STAThread] static int Main(string[] args) {
 if(args.Length==4&&args[0]=="--build-compat") {try {GamePatches.Build(args[1],args[2]);CompatPatch.Apply(args[2],args[3]);return 0;}catch(Exception e){Console.WriteLine(e.Message);return 1;}}
 if(args.Length==2&&args[0]=="--prepare") {try {using(var form=new Launcher()){string game=Path.GetFullPath(args[1]);if(Running(game))throw new Exception("게임이 실행 중입니다.");if(form.rally.Checked)GamePatches.Build(game,Path.Combine(Path.GetDirectoryName(game),"3kd2-modern.exe"));form.InstallWindow(game);Console.WriteLine("Game patch and display settings prepared.");return 0;}}catch(Exception e){Console.WriteLine(e.Message);return 1;}}
 if(args.Length==3&&args[0]=="--build-game") {try {Console.WriteLine(GamePatches.Build(args[1],args[2]));return 0;}catch(Exception e){Console.WriteLine(e.Message);return 1;}}
 if(args.Length==4&&args[0]=="--apply") {string target=args[2],source=args[3];try { try {if(!Process.GetProcessById(int.Parse(args[1])).WaitForExit(15000))throw new Exception("기존 런처 종료 대기시간 초과");}catch(ArgumentException){} if(!string.Equals(Hash(source),File.ReadAllText(Path.Combine(Path.GetDirectoryName(source),"SHA256.txt")).Trim(),StringComparison.OrdinalIgnoreCase))throw new Exception("SHA256 불일치");File.Copy(target,target+".bak",true);try {File.Copy(source,target,true);}catch {File.Copy(target+".bak",target,true);throw;}Process.Start(target);return 0;}catch(Exception e){MessageBox.Show("업데이트 실패: "+e.Message);return 1;} }
 if(args.Length==1&&args[0]=="--self-test") {Console.WriteLine("Version="+Assembly.GetExecutingAssembly().GetName().Version+"; Game="+File.Exists(DefaultGame)+"; Runtime="+File.Exists(Path.Combine(Root,@"runtime\cnc-ddraw\ddraw.dll"))+"; SHA256="+Hash(Application.ExecutablePath));return File.Exists(DefaultGame)&&File.Exists(Path.Combine(Root,@"runtime\cnc-ddraw\ddraw.dll"))?0:1;}
 Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);Application.Run(new Launcher());return 0;
 }
}
