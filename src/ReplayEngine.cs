using System;
using System.IO;
using System.Diagnostics;
using System.Security.Cryptography;
using System.Reflection;

internal static class ReplayEngine {
 static string Hash(byte[] bytes){using(var h=SHA256.Create())return BitConverter.ToString(h.ComputeHash(bytes)).Replace("-","");}
 static string Quote(string value){return "\""+value+"\"";}
 static string Install(){
  byte[] bytes;
  using(var input=Assembly.GetExecutingAssembly().GetManifestResourceStream("samchun-replay-engine.exe")){
   if(input==null)throw new InvalidOperationException("이 런처에는 새 리플레이 엔진이 없습니다. 최신 시험 런처를 사용하세요.");
   using(var output=new MemoryStream()){input.CopyTo(output);bytes=output.ToArray();}
  }
  string dir=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"SamchunLauncher","replay","1.3.57-"+Hash(bytes).Substring(0,16));
  Directory.CreateDirectory(dir);string engine=Path.Combine(dir,"samchun-replay-engine.exe");
  if(!File.Exists(engine)||Hash(File.ReadAllBytes(engine))!=Hash(bytes))File.WriteAllBytes(engine,bytes);
  using(var license=Assembly.GetExecutingAssembly().GetManifestResourceStream("replay-THIRD-PARTY.txt")){
   if(license!=null)using(var reader=new StreamReader(license))File.WriteAllText(Path.Combine(dir,"replay-THIRD-PARTY.txt"),reader.ReadToEnd());
  }
  return engine;
 }
 internal static string Work(){return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"SamchunLauncher","replay","sessions",Guid.NewGuid().ToString("N"));}
 internal static bool IsNew(string file){using(var f=File.OpenRead(file)){return f.ReadByte()==0x50&&f.ReadByte()==0x4b;}}
 internal static void Validate(string file){
  string work=Work();using(var p=Process.Start(new ProcessStartInfo(Install(),"validate --file "+Quote(file)+" --work "+Quote(work)){UseShellExecute=false,CreateNoWindow=true})){
   if(!p.WaitForExit(30000)){p.Kill();throw new InvalidDataException("리플레이 검사 시간이 초과됐습니다.");}if(p.ExitCode!=0){string log=Path.Combine(work,"error.log");throw new InvalidDataException("손상되거나 호환되지 않는 리플레이입니다.\r\n"+(File.Exists(log)?File.ReadAllText(log):log));}
  }
 }
 internal static void Bundle(string configured,string file){
  if(!IsNew(file))return;
  string work=Work();
  using(var p=Process.Start(new ProcessStartInfo(Install(),"bundle --game "+Quote(Path.GetFullPath(configured.Trim().Trim('"')))+" --file "+Quote(file)+" --work "+Quote(work)+" --no-dialog"){UseShellExecute=false,CreateNoWindow=true})){
   if(!p.WaitForExit(120000)){p.Kill();throw new InvalidDataException("리플레이 지도 포함 시간이 초과됐습니다.");}
   if(p.ExitCode!=0){string log=Path.Combine(work,"error.log");throw new InvalidDataException("이전 리플레이에 지도를 포함하지 못했습니다. 같은 지도 파일이 있는 PC에서 한 번 재생하거나 영구 저장해 주세요.\r\n"+(File.Exists(log)?File.ReadAllText(log):log));}
  }
 }
 internal static void Start(string configured,string file,string serverIp=null){
  if(file!=null){var loading=new ReplayLoading();loading.Show();System.Threading.ThreadPool.QueueUserWorkItem(delegate{try{StartPrepared(configured,file,serverIp,loading);}catch(Exception e){loading.BeginInvoke((Action)delegate{loading.Close();System.Windows.Forms.MessageBox.Show(e.Message,"리플레이 준비 실패");});}});return;}
  StartPrepared(configured,file,serverIp,null);
 }
 static void StartPrepared(string configured,string file,string serverIp,ReplayLoading loading){
  string selected=Path.GetFullPath(configured.Trim().Trim('"')),dir=Path.GetDirectoryName(selected);
  string original=ReplayWindow.ResolveOriginal(selected),baseline=Path.Combine(dir,"3kd2-replay-base.exe");
  GamePatches.Build(original,baseline);
  if(file!=null)Bundle(configured,file);
  string work=Work();
  string args=(file==null?"record":"play --file "+Quote(file))+" --game "+Quote(original)+" --baseline "+Quote(baseline)+" --work "+Quote(work);
  if(file==null&&serverIp!=null)args+=" --network-helper "+Quote(System.Windows.Forms.Application.ExecutablePath)+" --server-ip "+Quote(serverIp);
  var engineStart=new ProcessStartInfo(Install(),args){UseShellExecute=false,CreateNoWindow=true,WorkingDirectory=dir};
  // Native getenv(RENDER3D) overrides option.ini; honor the chosen file instead.
  engineStart.EnvironmentVariables.Remove("RENDER3D");
  Process process=Process.Start(engineStart);
  if(loading!=null)loading.BeginInvoke((Action)delegate{loading.Attach(process,work);});
 }
}

// Immediate, responsive loading UI. Stage percentages are milestones, not time estimates.
internal sealed class ReplayLoading : System.Windows.Forms.Form {
 [System.Runtime.InteropServices.DllImport("kernel32.dll")] static extern IntPtr OpenProcess(uint access,bool inherit,int pid);
 [System.Runtime.InteropServices.DllImport("kernel32.dll")] static extern bool ReadProcessMemory(IntPtr h,IntPtr p,byte[] b,int n,out IntPtr done);
 [System.Runtime.InteropServices.DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
 System.Windows.Forms.Label stage=new System.Windows.Forms.Label(),elapsed=new System.Windows.Forms.Label();System.Windows.Forms.ProgressBar bar=new System.Windows.Forms.ProgressBar();System.Windows.Forms.Timer timer=new System.Windows.Forms.Timer();Stopwatch clock=Stopwatch.StartNew();Process engine;string work;IntPtr memory;int ready,restored;
 System.Web.Script.Serialization.JavaScriptSerializer json=new System.Web.Script.Serialization.JavaScriptSerializer();
 protected override bool ShowWithoutActivation {get{return true;}}
 internal ReplayLoading(){Text="리플레이 로딩";ControlBox=false;FormBorderStyle=System.Windows.Forms.FormBorderStyle.FixedDialog;StartPosition=System.Windows.Forms.FormStartPosition.CenterScreen;TopMost=true;ClientSize=new System.Drawing.Size(440,150);Font=new System.Drawing.Font("맑은 고딕",10);stage.SetBounds(20,20,400,35);stage.Text="실행 파일 확인 및 리플레이 엔진 준비 중";bar.SetBounds(20,63,400,22);bar.Value=5;elapsed.SetBounds(20,102,400,30);Controls.Add(stage);Controls.Add(bar);Controls.Add(elapsed);timer.Interval=150;timer.Tick+=delegate{UpdateStage();};timer.Start();}
 internal void Attach(Process process,string directory){engine=process;work=directory;}
 int Read(int address){byte[] b=new byte[4];IntPtr done;return memory!=IntPtr.Zero&&ReadProcessMemory(memory,new IntPtr(address),b,4,out done)&&done.ToInt32()==4?BitConverter.ToInt32(b,0):-1;}
 void UpdateStage(){elapsed.Text="경과 시간 "+(int)clock.Elapsed.TotalSeconds+"초 · 단계 기준 진행 표시";if(engine==null)return;engine.Refresh();if(engine.HasExited){Close();return;}try{string path=Path.Combine(work,"loading.json");if(!File.Exists(path))return;var p=json.Deserialize<System.Collections.Generic.Dictionary<string,object>>(File.ReadAllText(path));stage.Text=Convert.ToString(p["text"]);bar.Value=Math.Max(0,Math.Min(100,Convert.ToInt32(p["percent"])));if(memory==IntPtr.Zero&&p["game_pid"]!=null){memory=OpenProcess(0x410,false,Convert.ToInt32(p["game_pid"]));var profile=json.Deserialize<System.Collections.Generic.Dictionary<string,object>>(File.ReadAllText(Path.Combine(work,"runtime.json")));ready=Convert.ToInt32(profile["autoload_status_address"]);restored=Convert.ToInt32(profile["restore_header"]);}if(Read(ready)==2&&Read(restored)==1){bar.Value=100;Close();}}catch(IOException){}catch(ArgumentException){} }
 protected override void OnFormClosed(System.Windows.Forms.FormClosedEventArgs e){timer.Dispose();if(memory!=IntPtr.Zero)CloseHandle(memory);base.OnFormClosed(e);}
}
