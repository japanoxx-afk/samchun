using System;using System.IO;using System.Reflection;using System.Diagnostics;
class TestEditorCompatibility {
 static void Require(bool result,string message){if(!result)throw new Exception(message);}
 static int Main(string[] args){
  var a=Assembly.LoadFile(Path.GetFullPath(args[0]));var type=a.GetType("EditorLaunch");
  var check=type.GetMethod("CompatibleLayout",BindingFlags.Static|BindingFlags.NonPublic);
  Func<byte[],bool> compatible=data=>(bool)check.Invoke(null,new object[]{data});
  byte[] original=File.ReadAllBytes(args[1]);Require(compatible(original),"Known editor rejected");
  var metadata=(byte[])original.Clone();int pe=BitConverter.ToInt32(metadata,0x3c);metadata[pe+8]^=1;metadata[0x2c9000+128]^=1;Require(compatible(metadata),"Metadata variant rejected");
  var code=(byte[])original.Clone();code[0x22776]^=1;Require(!compatible(code),"Changed code accepted");
  var layout=(byte[])original.Clone();layout[pe+24+28]^=1;Require(!compatible(layout),"Changed base accepted");
  Require(!compatible(new byte[0]),"Empty editor accepted");
  if(args.Length>2) {
   var upgrade=a.GetType("EditorUpgrade");byte[] legacy=File.ReadAllBytes(args[2]);
   Require((bool)upgrade.GetMethod("IsSource",BindingFlags.Static|BindingFlags.NonPublic).Invoke(null,new object[]{legacy}),"Provided build rejected");
   byte[] result=(byte[])upgrade.GetMethod("Apply",BindingFlags.Static|BindingFlags.NonPublic).Invoke(null,new object[]{legacy});
   Require(result.Length==original.Length,"Upgrade output length");for(int n=0;n<result.Length;n++)Require(result[n]==original[n],"Upgrade output differs");
   Require(compatible(legacy),"Provided editor compatibility rejected");
  }
  string temp=Path.Combine(Path.GetTempPath(),"samchun-editor-test-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(temp);
  try {
   foreach(string name in new[]{"3kd2.exe","3kd2edit.DBX","RES.PAK","PALETTE.PAK"})File.WriteAllBytes(Path.Combine(temp,name),new byte[0]);
   string editor=Path.Combine(temp,"3kd2Edit.exe");File.WriteAllBytes(editor,code);
   var start=(ProcessStartInfo)type.GetMethod("Prepare",BindingFlags.Static|BindingFlags.NonPublic).Invoke(null,new object[]{Path.Combine(temp,"3kd2.exe")});
   Require(start.FileName==editor&&start.WorkingDirectory==temp,"Unsupported editor fallback incorrect");
   Require(start.EnvironmentVariables["__COMPAT_LAYER"].Contains("16BITCOLOR"),"Missing fallback compatibility");
   Require(!File.Exists(Path.Combine(temp,"3kd2Edit-modern.exe")),"Unsupported executable modified");
   Require(File.ReadAllBytes(editor)[0x22776]==code[0x22776],"Original changed");
  }finally{foreach(string f in Directory.GetFiles(temp))File.Delete(f);Directory.Delete(temp);}
  Console.WriteLine("PASS: metadata variants, changed code/layout rejection, unsupported original fallback and color compatibility.");return 0;
 }
}
