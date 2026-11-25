using System;
using System.IO;
using System.Reflection;
using System.Text;
using System.Runtime.InteropServices;
using System.Collections.Generic;
using System.IO.Compression;

internal static class LauncherDiagnostics {
 [DllImport("shell32.dll",CharSet=CharSet.Unicode)]static extern int SHCreateDirectoryExW(IntPtr window,string path,IntPtr security);
 [DllImport("shell32.dll",CharSet=CharSet.Unicode)]static extern void SHChangeNotify(uint change,uint flags,string path,IntPtr second);
 internal static string Folder {get{return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"SamchunLauncher","ErrorLogs");}}
 internal static void OpenFolder(){
  int created=SHCreateDirectoryExW(IntPtr.Zero,Folder,IntPtr.Zero);if(created!=0&&created!=183)throw new System.ComponentModel.Win32Exception(created);
  SHChangeNotify(8,0x1005,Folder,IntPtr.Zero);
  System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo("explorer.exe","\""+Folder+"\""){UseShellExecute=true});
 }
 static IEnumerable<string> Logs(string directory,int depth){
  if(depth>3)return new string[0];var result=new List<string>();
  if(!Directory.Exists(directory))return result;
  foreach(string file in Directory.GetFiles(directory)){
   var info=new FileInfo(file);string ext=info.Extension.ToLowerInvariant();
   if((info.Attributes&FileAttributes.ReparsePoint)==0&&(ext==".log"||ext==".json"||ext==".txt"))result.Add(file);
  }
  foreach(string child in Directory.GetDirectories(directory))if((File.GetAttributes(child)&FileAttributes.ReparsePoint)==0)result.AddRange(Logs(child,depth+1));
  return result;
 }
 internal static void ExportZip(string target){ExportZip(target,Folder);}
 internal static void ExportZip(string target,string folder){
  folder=Path.GetFullPath(folder).TrimEnd('\\','/');Directory.CreateDirectory(folder);var files=new List<string>(Logs(folder,0));files.Sort((a,b)=>File.GetLastWriteTimeUtc(b).CompareTo(File.GetLastWriteTimeUtc(a)));
  string temp=target+"."+Guid.NewGuid().ToString("N")+".tmp";long total=0;int count=0,skipped=0;
  try{
   using(var output=new FileStream(temp,FileMode.CreateNew,FileAccess.Write))using(var zip=new ZipArchive(output,ZipArchiveMode.Create)){
    foreach(string file in files){try{var info=new FileInfo(file);if(count>=200||info.Length>2*1024*1024||total+info.Length>32*1024*1024){skipped++;continue;}
     using(var input=new FileStream(file,FileMode.Open,FileAccess.Read,FileShare.ReadWrite|FileShare.Delete)){
      string relative=file.Substring(folder.Length).TrimStart('\\','/').Replace('\\','/');
      using(var entry=zip.CreateEntry("ErrorLogs/"+relative,CompressionLevel.Optimal).Open()){
       byte[] buffer=new byte[16384];int n;long remaining=Math.Min(input.Length,2*1024*1024);
       while(remaining>0&&(n=input.Read(buffer,0,(int)Math.Min(buffer.Length,remaining)))>0){entry.Write(buffer,0,n);remaining-=n;total+=n;}
      }count++;
     }}catch(IOException){skipped++;}catch(UnauthorizedAccessException){skipped++;}}
    using(var writer=new StreamWriter(zip.CreateEntry("REPORT.txt").Open(),new UTF8Encoding(false)))writer.Write("삼국지 천명 2 오류 리포트\r\n런처: "+Assembly.GetExecutingAssembly().GetName().Version+"\r\n생성 시각: "+DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss")+"\r\n포함 로그: "+count+" / 제외: "+skipped+"\r\n최근 로그 우선 · 최대 200개/32MB · 파일당 2MB\r\n계정 DB, 비밀번호, 게임 및 리플레이 원본은 포함하지 않습니다. 자동 전송하지 않습니다.\r\n");
   }
   if(File.Exists(target))File.Replace(temp,target,null);else File.Move(temp,target);
  }finally{if(File.Exists(temp))File.Delete(temp);}
 }
 internal static string Save(Exception error){
  try{
   Directory.CreateDirectory(Folder);
   string file=Path.Combine(Folder,DateTime.UtcNow.AddHours(9).ToString("yyyy-MM-dd_HH-mm-ss")+"_launcher_"+Guid.NewGuid().ToString("N").Substring(0,8)+".log");
   File.WriteAllText(file,"삼국지 천명 2 런처 오류\r\n버전: "+Assembly.GetExecutingAssembly().GetName().Version+"\r\n발생 시각(UTC): "+DateTime.UtcNow.ToString("o")+"\r\nWindows: "+Environment.OSVersion+"\r\n\r\n"+error,new UTF8Encoding(false));
   return file;
  }catch{return null;}
 }
}
