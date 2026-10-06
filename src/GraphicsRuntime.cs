using System;
using System.IO;
using System.Reflection;
using System.Security.Cryptography;

static class GraphicsRuntime {
 internal static string Prepare() {
  string dir=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"SamchunLauncher","graphics",Assembly.GetExecutingAssembly().GetName().Version.ToString());
  Directory.CreateDirectory(dir);
  foreach(string name in new[]{"ddraw.dll","ddraw.ini","cnc-ddraw-LICENSE.txt"}) {
   byte[] data;
   using(var stream=Assembly.GetExecutingAssembly().GetManifestResourceStream("graphics."+name)) {
    if(stream==null)throw new InvalidDataException("내장 그래픽 파일이 없습니다: "+name);
    using(var output=new MemoryStream()){stream.CopyTo(output);data=output.ToArray();}
   }
   string file=Path.Combine(dir,name);bool same=false;
   using(var hash=SHA256.Create())if(File.Exists(file))same=Convert.ToBase64String(hash.ComputeHash(File.ReadAllBytes(file)))==Convert.ToBase64String(hash.ComputeHash(data));
   if(!same) {
    string temporary=file+"."+Guid.NewGuid().ToString("N")+".tmp";
    try{File.WriteAllBytes(temporary,data);if(File.Exists(file))File.Replace(temporary,file,null);else File.Move(temporary,file);}finally{if(File.Exists(temporary))File.Delete(temporary);}
   }
  }
  return dir;
 }
}
