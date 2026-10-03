using System;
using System.IO;
using System.Reflection;
using System.Collections.Generic;
class VerifyOnline {
 static Type updates,network;static int checks;
 static object Call(Type t,string method,params object[] args){return t.GetMethod(method,BindingFlags.NonPublic|BindingFlags.Static).Invoke(null,args);}
 static void Reject(Action a){try{a();}catch(TargetInvocationException e){if(e.InnerException is ArgumentException||e.InnerException is InvalidDataException){checks++;return;}throw;}throw new Exception("Expected rejection");}
 static void Main(string[] args){var a=Assembly.LoadFile(Path.GetFullPath(args[0]));updates=a.GetType("OnlineUpdate");network=a.GetType("NetworkPatch");
  Call(updates,"Verify",args[0],Call(updates,"Sha",args[0]),a.GetName().Version);checks++;
  Reject(()=>Call(updates,"Verify",args[0],new string('0',64),a.GetName().Version));
  Reject(()=>Call(updates,"Verify",args[0],Call(updates,"Sha",args[0]),new Version(9,0,0,0)));
  foreach(string ip in new[]{"127.0.0.1","192.168.1.5"}){Call(network,"Validate",false,"Player",ip);checks++;}
  foreach(string ip in new[]{"0.0.0.0","255.255.255.255","::1","bad"})Reject(()=>Call(network,"Validate",false,"Player",ip));
  Reject(()=>Call(network,"Validate",true,new string('a',16),""));Reject(()=>Call(network,"Validate",true,"",""));
  var release=new Dictionary<string,object>{{"assets",new object[]{new Dictionary<string,object>{{"name","launcher.exe"},{"browser_download_url","https://evil.test/launcher.exe"}}}}};Reject(()=>Call(updates,"Asset",release,"launcher.exe"));
  var build=a.GetType("GamePatches").GetMethod("Build");foreach(bool host in new[]{true,false}){string output=Path.Combine(args[2],host?"network-host.exe":"network-join.exe");build.Invoke(null,new object[]{args[1],output});Call(network,"Apply",output,host,"Player","127.0.0.1");checks++;}
  Console.WriteLine("Online/update validation: "+checks+" checks passed");
 }
}
