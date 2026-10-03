using System;
using System.IO;
using System.Diagnostics;
using System.Drawing;
using System.Windows.Forms;
using System.Security.Cryptography;
using System.Reflection;
using System.Threading;
using System.Runtime.InteropServices;

[assembly: AssemblyVersion("1.1.7.0")]
class Launcher : Form {
 const string DefaultGame = @"C:\Users\seo\Downloads\DGGL\Games\3KD2120g_Win\3kd2.exe";
 static string Root = AppDomain.CurrentDomain.BaseDirectory;
 TextBox path = new TextBox(); CheckBox window = new CheckBox(); Label status = new Label();
 ComboBox resolution = new ComboBox(); CheckBox stretch = new CheckBox();
 CheckBox rally = new CheckBox();
 static readonly string[] Resolutions = {"1280 × 720 (16:9)", "1600 × 900 (16:9)", "1920 × 1080 (16:9)", "2560 × 1440 (16:9)", "3840 × 2160 (16:9)", "1280 × 960 (4:3)"};
 static readonly int[] Widths = {1280,1600,1920,2560,3840,1280}, Heights = {720,900,1080,1440,2160,960};
 [DllImport("kernel32", CharSet=CharSet.Unicode)] static extern bool WritePrivateProfileString(string section,string key,string value,string file);
 static string Hash(string file) { using(var s=File.OpenRead(file)) using(var h=SHA256.Create()) return BitConverter.ToString(h.ComputeHash(s)).Replace("-",""); }
 static string Quote(string s) { return "\""+s+"\""; }
 static bool Running(string game) { foreach(string name in new[]{Path.GetFileNameWithoutExtension(game),"3kd2-modern"})foreach(var p in Process.GetProcessesByName(name)) { try { if(string.Equals(Path.GetDirectoryName(p.MainModule.FileName),Path.GetDirectoryName(game),StringComparison.OrdinalIgnoreCase)) return true; } catch { return true; } } return false; }
 static void Backup(string dir,string name) { string f=Path.Combine(dir,name), b=Path.Combine(dir,"launcher-backup",name); Directory.CreateDirectory(Path.GetDirectoryName(b)); if(File.Exists(f)&&!File.Exists(b)) File.Copy(f,b); }
 void Guard(Action action) { try { action(); } catch(Exception e) { status.Text="실패: "+e.Message; MessageBox.Show(e.Message,"작업 실패"); } }
 Button Button(string text,int y,Action action) { var b=new Button {Text=text,Left=28,Top=y,Width=584,Height=38}; b.Click+=(s,e)=>Guard(action); Controls.Add(b); return b; }
 public Launcher() {
 Text="삼국지 천명 2 런처 · 1.1.7"; ClientSize=new Size(640,755); Font=new Font("맑은 고딕",10); FormBorderStyle=FormBorderStyle.FixedSingle; MaximizeBox=false;
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
 Button("게임 실행",326,()=>{string game=Path.GetFullPath(path.Text); if(!File.Exists(game))throw new Exception("게임 파일을 찾을 수 없습니다."); if(Running(game))throw new Exception("게임이 이미 실행 중입니다."); string launch=rally.Checked?GamePatches.Build(game,Path.Combine(Path.GetDirectoryName(game),"3kd2-modern.exe")):game; InstallWindow(game); File.WriteAllText(Path.Combine(Root,"game-path.txt"),game); Process.Start(new ProcessStartInfo(launch){WorkingDirectory=Path.GetDirectoryName(game),UseShellExecute=true}); status.Text="게임 실행 요청 · "+(rally.Checked?"랠리 패치 사용":"원본 게임");});
 Button("해상도 / 화면모드 설정 적용",373,()=>{InstallWindow(Path.GetFullPath(path.Text));status.Text="설정 적용: "+resolution.Text+" · "+(window.Checked?"창모드":"전체화면")+". Alt+Enter로 전환 가능.";});
 Button("기존 그래픽 DLL / 설정 복원",420,()=>{string game=Path.GetFullPath(path.Text),dir=Path.GetDirectoryName(game),backup=Path.Combine(dir,"launcher-backup");if(Running(game))throw new Exception("게임을 종료한 뒤 복원하세요.");if(!File.Exists(Path.Combine(backup,"ddraw.dll")))throw new Exception("복원할 백업이 없습니다.");File.Copy(Path.Combine(backup,"ddraw.dll"),Path.Combine(dir,"ddraw.dll"),true);if(File.Exists(Path.Combine(backup,"ddraw.ini")))File.Copy(Path.Combine(backup,"ddraw.ini"),Path.Combine(dir,"ddraw.ini"),true);else if(File.Exists(Path.Combine(backup,"ini-was-absent")))File.Delete(Path.Combine(dir,"ddraw.ini"));window.Checked=false;rally.Checked=false;status.Text="기존 그래픽 설정 복원 완료. 원본 게임을 직접 실행하면 원복 상태로 실행됩니다.";});
 Button("런처 업데이트",467,ApplyUpdate);
 Controls.Add(new Label {Left=28,Top=519,Width=584,Height=155,Text="랠리: 건물 선택 후 땅 또는 자원 우클릭 → 랠리 지정\r\n기·오어에 우클릭 또는 수동 랠리 지정 → 생산 후 채집.\r\nF2: 전장 군사 선택 / . : 쉬는 일꾼 선택 (최대 32기)\r\n\r\n미구현: 마나 65% / 선택 수 확대\r\n복수건물 동시생산 / 순차시전"});
 status.SetBounds(28,690,584,60);status.Text="준비 완료 · 원본 EXE 보존, 패치 실행 파일은 별도로 생성합니다.";Controls.Add(status);
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
 static string FindUpdate(string root,Version current) {
 string selected=null;Version newest=current;
 string parent=Directory.GetParent(Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar)).FullName;
 foreach(string folder in new[]{Path.Combine(root,"updates"),Path.Combine(parent,"updates")}) {
 string source=Path.Combine(folder,"launcher.exe"),checksum=Path.Combine(folder,"SHA256.txt");
 if(!File.Exists(source)||!File.Exists(checksum))continue;
 var info=AssemblyName.GetAssemblyName(source);
 if(info.Name!="launcher"||info.Version<=newest)continue;
 if(!string.Equals(Hash(source),File.ReadAllText(checksum).Trim(),StringComparison.OrdinalIgnoreCase))throw new Exception("업데이트 파일 검증에 실패했습니다.");
 selected=source;newest=info.Version;
 }
 return selected;
 }
 void ApplyUpdate() {
 string source=FindUpdate(Root,Assembly.GetExecutingAssembly().GetName().Version);
 if(source==null){status.Text="적용할 새 업데이트가 없습니다.";return;}
 string expected=Hash(source);
 string stage=Path.Combine(Path.GetTempPath(),"3kd2-update-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(stage);File.Copy(source,Path.Combine(stage,"launcher.new.exe"));File.WriteAllText(Path.Combine(stage,"SHA256.txt"),expected);string helper=Path.Combine(stage,"helper.exe");File.Copy(Application.ExecutablePath,helper);
 Process.Start(new ProcessStartInfo(helper,"--apply "+Process.GetCurrentProcess().Id+" "+Quote(Application.ExecutablePath)+" "+Quote(Path.Combine(stage,"launcher.new.exe"))){UseShellExecute=false});Application.Exit();
 }
 [STAThread] static int Main(string[] args) {
 if(args.Length==2&&args[0]=="--prepare") {try {using(var form=new Launcher()){string game=Path.GetFullPath(args[1]);if(Running(game))throw new Exception("게임이 실행 중입니다.");if(form.rally.Checked)GamePatches.Build(game,Path.Combine(Path.GetDirectoryName(game),"3kd2-modern.exe"));form.InstallWindow(game);Console.WriteLine("Game patch and display settings prepared.");return 0;}}catch(Exception e){Console.WriteLine(e.Message);return 1;}}
 if(args.Length==3&&args[0]=="--build-game") {try {Console.WriteLine(GamePatches.Build(args[1],args[2]));return 0;}catch(Exception e){Console.WriteLine(e.Message);return 1;}}
 if(args.Length==4&&args[0]=="--apply") {string target=args[2],source=args[3];try { try {if(!Process.GetProcessById(int.Parse(args[1])).WaitForExit(15000))throw new Exception("기존 런처 종료 대기시간 초과");}catch(ArgumentException){} if(!string.Equals(Hash(source),File.ReadAllText(Path.Combine(Path.GetDirectoryName(source),"SHA256.txt")).Trim(),StringComparison.OrdinalIgnoreCase))throw new Exception("SHA256 불일치");File.Copy(target,target+".bak",true);try {File.Copy(source,target,true);}catch {File.Copy(target+".bak",target,true);throw;}Process.Start(target);return 0;}catch(Exception e){MessageBox.Show("업데이트 실패: "+e.Message);return 1;} }
 if(args.Length==1&&args[0]=="--self-test") {Console.WriteLine("Version="+Assembly.GetExecutingAssembly().GetName().Version+"; Game="+File.Exists(DefaultGame)+"; Runtime="+File.Exists(Path.Combine(Root,@"runtime\cnc-ddraw\ddraw.dll"))+"; SHA256="+Hash(Application.ExecutablePath));return File.Exists(DefaultGame)&&File.Exists(Path.Combine(Root,@"runtime\cnc-ddraw\ddraw.dll"))?0:1;}
 Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);Application.Run(new Launcher());return 0;
 }
}
