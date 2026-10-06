using System;
using System.IO;
using System.Net;
using System.Reflection;
using System.Security.Cryptography;
using System.Web.Script.Serialization;
using System.Collections.Generic;

static class OnlineUpdate {
 internal const string Repository="https://github.com/japanoxx-afk/samchun";
 const string Api="https://api.github.com/repos/japanoxx-afk/samchun/releases?per_page=100";
 internal static string Sha(string file) {using(var s=File.OpenRead(file))using(var h=SHA256.Create())return BitConverter.ToString(h.ComputeHash(s)).Replace("-","");}
 static byte[] Get(string url,int limit) {
  var request=(HttpWebRequest)WebRequest.Create(url);request.UserAgent="samchun-launcher";request.Timeout=15000;request.ReadWriteTimeout=15000;
  using(var response=request.GetResponse())using(var s=response.GetResponseStream())using(var m=new MemoryStream()) {
   byte[] buffer=new byte[16384];int n;while((n=s.Read(buffer,0,buffer.Length))>0){if(m.Length+n>limit)throw new InvalidDataException("업데이트 파일 크기 제한 초과");m.Write(buffer,0,n);}return m.ToArray();
  }
 }
 internal static string Asset(Dictionary<string,object> release,string name) {
  var assets=release["assets"] as System.Collections.IEnumerable;if(assets==null)throw new InvalidDataException("릴리스 파일 목록 오류");
  foreach(object item in assets){var a=(Dictionary<string,object>)item;if((string)a["name"]!=name)continue;
   string url=(string)a["browser_download_url"];Uri uri;
   if(!Uri.TryCreate(url,UriKind.Absolute,out uri)||uri.Scheme!="https"||uri.Host!="github.com"||!uri.AbsolutePath.StartsWith("/japanoxx-afk/samchun/releases/download/",StringComparison.Ordinal))throw new InvalidDataException("업데이트 다운로드 주소 오류");return url;
  }throw new InvalidDataException("릴리스에 "+name+" 파일이 없습니다.");
 }
 internal static void Verify(string file,string expected,Version version) {
  expected=expected.Trim();if(expected.Length!=64||!string.Equals(Sha(file),expected,StringComparison.OrdinalIgnoreCase))throw new InvalidDataException("업데이트 SHA256 검증 실패");
  var info=AssemblyName.GetAssemblyName(file);if(info.Name!="launcher"||info.Version!=version)throw new InvalidDataException("업데이트 버전 또는 실행 파일 불일치");
 }
 internal static Dictionary<string,object> SelectRelease(object[] releases,Version current) {
  Dictionary<string,object> selected=null;Version best=current;
  foreach(object item in releases) {
   var candidate=item as Dictionary<string,object>;if(candidate==null||(bool)candidate["draft"])continue;
   Version version;string tag=((string)candidate["tag_name"]).TrimStart('v');int suffix=tag.IndexOf('-');if(suffix>=0)tag=tag.Substring(0,suffix);
   if(!Version.TryParse(tag,out version))continue;
   version=new Version(version.Major,version.Minor,Math.Max(0,version.Build),Math.Max(0,version.Revision));
   if(version<=best)continue;
   try{Asset(candidate,"launcher.exe");Asset(candidate,"SHA256.txt");}catch(InvalidDataException){continue;}
   best=version;selected=candidate;
  }
  return selected;
 }
 internal static string Download(Version current) {
  ServicePointManager.SecurityProtocol=(SecurityProtocolType)3072;
  byte[] json;
  try{json=Get(Api,1024*1024);}catch(WebException e){var r=e.Response as HttpWebResponse;if(r!=null&&r.StatusCode==HttpStatusCode.NotFound)throw new InvalidOperationException("공개된 업데이트 릴리스가 아직 없습니다.");throw;}
  var releases=new JavaScriptSerializer().Deserialize<object[]>(System.Text.Encoding.UTF8.GetString(json));
  var release=SelectRelease(releases,current);if(release==null)return null;
  string tag=((string)release["tag_name"]).TrimStart('v');int suffix=tag.IndexOf('-');if(suffix>=0)tag=tag.Substring(0,suffix);
  Version v;if(!Version.TryParse(tag,out v))throw new InvalidDataException("릴리스 버전 오류");
  v=new Version(v.Major,v.Minor,Math.Max(0,v.Build),Math.Max(0,v.Revision));if(v<=current)return null;
  string executable=Asset(release,"launcher.exe"),checksum=Asset(release,"SHA256.txt");
  string expected=System.Text.Encoding.ASCII.GetString(Get(checksum,1024)).Trim();
  string stage=Path.Combine(Path.GetTempPath(),"3kd2-update-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(stage);
  try {string file=Path.Combine(stage,"launcher.new.exe");File.WriteAllBytes(file,Get(executable,32*1024*1024));Verify(file,expected,v);File.WriteAllText(Path.Combine(stage,"SHA256.txt"),expected);return file;}
  catch{Directory.Delete(stage,true);throw;}
 }
}

