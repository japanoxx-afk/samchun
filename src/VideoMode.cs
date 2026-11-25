using System;
using System.IO;
using System.Text;

internal static class VideoMode {
 internal static readonly string[] Names={"Auto Detect (자동 감지)","Direct3D","Voodoo","Software"};
 // Native 571020 option.ini jump table: 0=auto, 1=D3D, 2=software, 3=Voodoo.
 static readonly int[] Values={0,1,3,2};
 internal static int Read(string game){
  try{string file=Path.Combine(Path.GetDirectoryName(Path.GetFullPath(game)),"option.ini");if(!File.Exists(file)||new FileInfo(file).Length>32)return 0;int value;if(int.TryParse(File.ReadAllText(file).Trim(),out value))return Math.Max(0,Array.IndexOf(Values,value));}catch(ArgumentException){}catch(IOException){}catch(UnauthorizedAccessException){}
  return 0;
 }
 internal static void Save(string game,int index){
  if(index<0||index>=Values.Length)throw new ArgumentOutOfRangeException("index");
  if(!File.Exists(game))throw new FileNotFoundException("게임 파일을 찾을 수 없습니다.",game);
  string dir=Path.GetDirectoryName(Path.GetFullPath(game)),file=Path.Combine(dir,"option.ini"),backup=Path.Combine(dir,"launcher-backup","option.ini");
  if(File.Exists(file)&&!File.Exists(backup)){Directory.CreateDirectory(Path.GetDirectoryName(backup));File.Copy(file,backup);}
  string temporary=file+"."+Guid.NewGuid().ToString("N")+".tmp";
  try{File.WriteAllText(temporary,Values[index]+"\r\n",Encoding.ASCII);if(File.Exists(file))File.Replace(temporary,file,null);else File.Move(temporary,file);}finally{if(File.Exists(temporary))File.Delete(temporary);}
 }
}
