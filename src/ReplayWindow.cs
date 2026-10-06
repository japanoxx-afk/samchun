using System;
using System.IO;
using System.IO.Compression;
using System.Text;
using System.Diagnostics;
using System.Drawing;
using System.Windows.Forms;
using System.Security.Cryptography;

class ReplayWindow : Form {
 const string GameHash="A0EE96931B3B74FCE739062D8E58253892510EF863E9127648AC38FD4D515F99";
 const string RuntimeHash="8D2AA2962DE6AC1577BE14982E5AB55F4D6D8D7A6AA1B026CF3BE9D4665A754E";
 const string SaveHash="DB015576F7AF34CC913B2485F17B083D0ADCDD96FF8F0467CB733EA5F30D3CF4";
 readonly string game,folder; ListBox list=new ListBox(); Label message=new Label();
 static string Hash(byte[] b){using(var h=SHA256.Create())return BitConverter.ToString(h.ComputeHash(b)).Replace("-","");}
 internal ReplayWindow(string gamePath) {
  game=Path.GetFullPath(gamePath.Trim().Trim('"'));folder=Path.Combine(Path.GetDirectoryName(game),"Replays");Directory.CreateDirectory(folder);
  string sample=Path.Combine(folder,"2026-10-07_00-00-00_test.screplay");
  if(!File.Exists(Path.Combine(folder,".test-installed")))using(var stream=System.Reflection.Assembly.GetExecutingAssembly().GetManifestResourceStream("replay-test.screplay")) {
   if(stream!=null){if(!File.Exists(sample))using(var output=File.Create(sample)){stream.CopyTo(output);}File.WriteAllText(sample+".keep","permanent-test");File.WriteAllText(Path.Combine(folder,".test-installed"),"1");}
  }
  Text="리플레이 · 시험 기능";ClientSize=new Size(700,440);Font=new Font("맑은 고딕",10);StartPosition=FormStartPosition.CenterParent;
  Controls.Add(new Label{Text="지원: 저장 상태 기반 싱글 시험 기록 · 이동/채집/생산 명령 8건\r\n새 경기 자동 기록·멀티·관전 UI·배속은 아직 지원하지 않습니다.",Left=16,Top=12,Width=668,Height=54});
  list.SetBounds(16,76,668,220);Controls.Add(list);
  Add("선택 재생",16,()=>Play(Selected()));Add("파일 열기",150,()=>{using(var d=new OpenFileDialog{Filter="삼국지 천명2 리플레이|*.screplay"})if(d.ShowDialog(this)==DialogResult.OK){Validate(d.FileName);string dest=Path.Combine(folder,Path.GetFileName(d.FileName));if(!File.Exists(dest))File.Copy(d.FileName,dest);RefreshList();list.SelectedItem=Path.GetFileName(dest);}});
  Add("영구 저장",284,()=>{string file=Selected();File.WriteAllText(file+".keep","permanent");message.Text="영구 저장했습니다. 자동 정리 대상에서 제외됩니다.";});
  Add("삭제",418,()=>{string file=Selected();if(MessageBox.Show(this,Path.GetFileName(file)+" 삭제?","리플레이 삭제",MessageBoxButtons.YesNo)==DialogResult.Yes){File.Delete(file);if(File.Exists(file+".keep"))File.Delete(file+".keep");RefreshList();}});
  Add("폴더 열기",552,()=>Process.Start(new ProcessStartInfo("explorer.exe","\""+folder+"\""){UseShellExecute=true}));
  message.SetBounds(16,350,668,74);message.Text="시험 리플레이는 원본 1.20g 게임 데이터가 필요합니다. 기존 저장은 덮어쓰지 않습니다.";Controls.Add(message);RefreshList();
 }
 void Add(string text,int x,Action action){var b=new Button{Text=text,Left=x,Top=308,Width=128,Height=34};b.Click+=(s,e)=>{try{action();}catch(Exception ex){message.Text=ex.Message;MessageBox.Show(this,ex.Message,"리플레이 오류");}};Controls.Add(b);}
 void RefreshList(){list.Items.Clear();foreach(string f in Directory.GetFiles(folder,"*.screplay"))list.Items.Add(Path.GetFileName(f));if(list.Items.Count>0)list.SelectedIndex=0;}
 string Selected(){if(list.SelectedItem==null)throw new InvalidOperationException("리플레이를 선택하세요.");return Path.Combine(folder,(string)list.SelectedItem);}
 static byte[][] Validate(string file) {
  using(var f=File.OpenRead(file))using(var r=new BinaryReader(f)) {
   if(f.Length>20000000||Encoding.ASCII.GetString(r.ReadBytes(5))!="SRPL1")throw new InvalidDataException("손상되거나 지원하지 않는 기록 형식입니다.");
   byte[][] parts=new byte[3][];int[] limits={16384,16000000,1000000};
   for(int i=0;i<3;i++) {
    int size=r.ReadInt32();if(size<=0||size>limits[i]||size>f.Length-f.Position)throw new InvalidDataException("리플레이 데이터 길이 오류");
    byte[] packed=r.ReadBytes(size);using(var input=new MemoryStream(packed))using(var z=new GZipStream(input,CompressionMode.Decompress))using(var output=new MemoryStream()) {
     byte[] buffer=new byte[8192];int n;while((n=z.Read(buffer,0,buffer.Length))>0){if(output.Length+n>limits[i])throw new InvalidDataException("리플레이 압축 크기 제한 초과");output.Write(buffer,0,n);}parts[i]=output.ToArray();
    }
   }
   if(f.Position!=f.Length)throw new InvalidDataException("리플레이 뒤에 잘못된 데이터가 있습니다.");
   if(Hash(parts[1])!=RuntimeHash||Hash(parts[2])!=SaveHash)throw new InvalidDataException("손상되거나 현재 시뮬레이션과 호환되지 않는 리플레이입니다.");
   string metadata=Encoding.UTF8.GetString(parts[0]);
   if(metadata!="format=1\ngame="+GameHash+"\nsimulation=replay-stable-ids-experiment-1\nmap=RPLTEST\nparticipants=slot0\nframes=4604-6554\ncommands=8\n")throw new InvalidDataException("리플레이 메타데이터 호환성 검사 실패");
   return parts;
  }
 }
 internal static string ResolveOriginal(string configured) {
  string selected=Path.GetFullPath(configured.Trim().Trim('"')),dir=Path.GetDirectoryName(selected);
  foreach(string candidate in new[]{selected,Path.Combine(dir,"3kd2.exe"),Path.Combine(dir,"launcher-backup","3kd2.exe"),Path.Combine(dir,"launcher-backup","replay-original-1.20g.exe")})
   if(File.Exists(candidate)&&Hash(File.ReadAllBytes(candidate))==GameHash)return candidate;
  string actual=File.Exists(selected)?Hash(File.ReadAllBytes(selected)):"파일 없음";
  throw new InvalidDataException("게임 경로: "+selected+"\r\nSHA-256: "+actual+"\r\n\r\n이 기록과 호환되는 원본 1.20g를 게임 폴더 및 launcher-backup에서 찾지 못했습니다. 경로 오류와 버전 차이는 별개입니다. 원본 3kd2.exe를 선택해 주세요. 지원하지 않는 버전에 패치를 적용하지 않습니다.");
 }
 void Play(string file) {
  byte[][] parts=Validate(file);
  string original=ResolveOriginal(game);
  foreach(string name in new[]{"3kd2","3kd2-modern","3kd2-replay"})if(Process.GetProcessesByName(name).Length>0)throw new InvalidOperationException("게임을 종료한 뒤 재생하세요.");
  string dir=Path.GetDirectoryName(game),save=Path.Combine(dir,"SAVE","RPLTEST.SAV");
  if(File.Exists(save)&&Hash(File.ReadAllBytes(save))!=SaveHash)throw new InvalidOperationException("기존 RPLTEST.SAV가 달라 덮어쓰지 않습니다. 해당 저장 파일을 다른 이름으로 보관한 뒤 재생하세요.");
  Directory.CreateDirectory(Path.GetDirectoryName(save));if(!File.Exists(save))File.WriteAllBytes(save,parts[2]);
  string runtime=Path.Combine(dir,"3kd2-replay.exe");File.WriteAllBytes(runtime,parts[1]);
  Process.Start(new ProcessStartInfo(runtime){WorkingDirectory=dir,UseShellExecute=false});
  message.Text="자동 복원·재생을 시작했습니다. 시험 기록 끝에서는 일시정지됩니다. 게임 종료는 직접 해 주세요.";
 }
}
