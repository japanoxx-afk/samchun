using System;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
class VerifyLauncher {
 [DllImport("kernel32",CharSet=CharSet.Unicode)]static extern int GetPrivateProfileString(string section,string key,string fallback,StringBuilder text,int size,string file);
 static string Get(string section,string key,string file){var b=new StringBuilder(100);GetPrivateProfileString(section,key,"MISSING",b,100,file);return b.ToString();}
 static int Main(string[] args){
 string dir=Path.GetFullPath(args[1]);Directory.CreateDirectory(dir);string config=Path.Combine(dir,"ddraw.ini");
 var assembly=Assembly.LoadFrom(Path.GetFullPath(args[0]));var type=assembly.GetType("Launcher");var configure=type.GetMethod("ConfigureDisplay",BindingFlags.NonPublic|BindingFlags.Static);
 int[] widths={1280,1600,1920,2560,3840,1280},heights={720,900,1080,1440,2160,960};int count=0;
 for(int i=0;i<6;i++)foreach(bool fill in new[]{true,false})foreach(bool window in new[]{true,false}){
 configure.Invoke(null,new object[]{config,i,fill,window});
 foreach(string section in new[]{"ddraw","3kd2","3kd2.exe","3kd2-modern","3kd2-modern.exe"}){
 if(Get(section,"width",config)!=widths[i].ToString()||Get(section,"height",config)!=heights[i].ToString()||Get(section,"maintas",config)!=(fill?"false":"true")||Get(section,"windowed",config)!=(window?"true":"false")||Get(section,"savesettings",config)!="0"||Get(section,"adjmouse",config)!="true")throw new Exception("Display config mismatch");count++;
 }}
 string game=args[2],output=Path.Combine(dir,"3kd2-modern.exe");var patches=assembly.GetType("GamePatches");patches.GetMethod("Build").Invoke(null,new object[]{game,output});
 Console.WriteLine(count+" display configuration checks passed; patched executable generated: "+output);
 return 0;
 }
}
