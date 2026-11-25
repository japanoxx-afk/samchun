using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Net;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;

// Automatic replay upload to the RTS ARENA match site (rtsarena repository, POST /api/samchun/replays).
// Scans <game folder>\Replays every 30 seconds. Only network matches with two or more named players
// are sent; single-player games (player + computer), diagnostic/test recordings and unfinished files
// are never uploaded. The site links each replay to the internet server's match record.
static class ArenaUpload {
 internal const string DefaultSite="http://112.159.73.235:30013";
 const long MaxBytes=64L*1024*1024;            // same limit as the site (arena/games/samchun.py)
 const int SettleSeconds=15;                     // the replay writer renames .writing -> .screplay when done
 static readonly string StateFile=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"SamchunLauncher","arena-upload.json");
 static readonly object Gate=new object();
 static Timer timer;
 static Func<string> folderSource;
 static string site=DefaultSite;
 static int busy;
 internal static string Status="";
 internal static event Action<string> StatusChanged;

 // Status stored per file (name|size|write time): uploaded, duplicate, skipped:<reason>, rejected:<message>.
 // Network/authentication failures are not stored, so the file is retried on the next scan.
 internal static void Start(Func<string> replayFolder,string url) {
  folderSource=replayFolder;site=string.IsNullOrEmpty(url)?DefaultSite:url.TrimEnd('/');
  if(timer==null)timer=new Timer(delegate{ScanSafe();},null,5000,30000);
 }
 internal static void Stop() {if(timer!=null){timer.Dispose();timer=null;}Report("자동 업로드 꺼짐");}
 internal static string ReplayFolder(string gamePath) {
  try{return Path.Combine(Path.GetDirectoryName(Path.GetFullPath(gamePath.Trim().Trim('"'))),"Replays");}catch(Exception){return null;}
 }
 static void Report(string text){Status=text;var handler=StatusChanged;if(handler!=null)try{handler(text);}catch(Exception){}}
 static void ScanSafe() {
  if(Interlocked.Exchange(ref busy,1)==1)return;
  try{string folder=folderSource==null?null:folderSource();if(folder!=null)Scan(folder,site,ArenaSecret.Token,DateTime.UtcNow);}
  catch(Exception e){Report("업로드 오류: "+e.Message);}
  finally{Interlocked.Exchange(ref busy,0);}
 }

 // Returns one line per file handled in this pass (used by --arena-upload and tests).
 internal static List<string> Scan(string folder,string url,string token,DateTime nowUtc) {
  var handled=new List<string>();
  if(!Directory.Exists(folder))return handled;
  Dictionary<string,string> state;
  lock(Gate)state=Load();
  int sent=0,failed=0;string lastError=null;
  foreach(string file in Directory.GetFiles(folder,"*.screplay")) {
   var info=new FileInfo(file);
   if((nowUtc-info.LastWriteTimeUtc).TotalSeconds<SettleSeconds)continue;
   string key=info.Name+"|"+info.Length+"|"+info.LastWriteTimeUtc.Ticks;
   if(state.ContainsKey(key))continue;
   string result;
   string reason=Inspect(file,info.Length);
   if(reason!=null)result="skipped:"+reason;
   else {
    string error;result=Send(file,url,token,out error);
    if(result==null){failed++;lastError=error;handled.Add(info.Name+" retry "+error);continue;}
    if(result=="uploaded"||result=="duplicate"||result=="merged"||result=="created")sent++;
   }
   state[key]=result;handled.Add(info.Name+" "+result);
   lock(Gate)Save(state);
  }
  if(failed>0)Report("전적 사이트 업로드 실패 ("+lastError+") · 30초 뒤 다시 시도");
  else if(sent>0)Report("리플레이 "+sent+"개를 전적 사이트에 올렸습니다");
  else if(Status==""||Status.StartsWith("전적 사이트 업로드 실패"))Report("자동 업로드 켜짐 · 대전 리플레이를 기다리는 중");
  return handled;
 }

 // null = upload; otherwise why this file is not a ranked match replay.
 internal static string Inspect(string file,long length) {
  string name=Path.GetFileName(file);
  if(name.Contains("_test")||name.Contains("_diagnostic"))return "test";
  if(length<=0||length>MaxBytes)return "size";
  try {
   using(var stream=File.OpenRead(file))using(var zip=new ZipArchive(stream,ZipArchiveMode.Read)) {
    var entry=zip.GetEntry("metadata.json");
    if(entry==null||entry.Length>16384||zip.GetEntry("checkpoint.sav")==null||zip.GetEntry("record.journal")==null)return "format";
    string text;using(var reader=new StreamReader(entry.Open(),Encoding.UTF8))text=reader.ReadToEnd();
    var meta=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(text);
    if(meta==null||!"samchun-replay".Equals(meta.ContainsKey("kind")?meta["kind"]:null))return "format";
    if(Flag(meta,"diagnostic_only")||"diagnostic".Equals(meta.ContainsKey("completion")?meta["completion"]:null))return "diagnostic";
    if(!Flag(meta,"multiplayer"))return "single";
    int named=0;var seen=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
    object list;
    if(meta.TryGetValue("participants",out list)&&list is System.Collections.IEnumerable)
     foreach(object row in (System.Collections.IEnumerable)list) {
      var p=row as Dictionary<string,object>;if(p==null||!p.ContainsKey("id"))continue;
      string id=Convert.ToString(p["id"]).Trim();if(id.Length>0&&seen.Add(id))named++;
     }
    return named>=2?null:"single";
   }
  } catch(InvalidDataException){return "format";}
  catch(ArgumentException){return "format";}
  catch(InvalidOperationException){return "format";}
  catch(IOException){return "format";}
 }
 static bool Flag(Dictionary<string,object> meta,string key){object v;return meta.TryGetValue(key,out v)&&v is bool&&(bool)v;}

 // Returns the stored status, or null for a temporary failure (network, server error, wrong token).
 static string Send(string file,string url,string token,out string error) {
  error=null;
  try {
   byte[] data=File.ReadAllBytes(file);
   var request=(HttpWebRequest)WebRequest.Create(url.TrimEnd('/')+"/api/samchun/replays");
   request.Method="POST";request.ContentType="application/octet-stream";request.UserAgent="samchun-launcher";
   request.Timeout=60000;request.ReadWriteTimeout=60000;request.ContentLength=data.Length;
   request.Headers["X-Arena-Token"]=token??"";
   request.Headers["X-Filename"]=Uri.EscapeDataString(Path.GetFileName(file));
   using(var body=request.GetRequestStream())body.Write(data,0,data.Length);
   using(var response=(HttpWebResponse)request.GetResponse())return StatusOf(Read(response),"uploaded");
  } catch(WebException e) {
   var response=e.Response as HttpWebResponse;
   if(response!=null)using(response) {
    int code=(int)response.StatusCode;string text=Read(response);
    if(code==422||code==413)return "rejected:"+Message(text);
    error=code==401?"업로드 키가 맞지 않습니다 · 런처 업데이트 필요":"서버 응답 "+code;return null;
   }
   error="연결 실패";return null;
  } catch(IOException e){error=e.Message;return null;}
 }
 static string Read(HttpWebResponse response){using(var s=new StreamReader(response.GetResponseStream(),Encoding.UTF8))return s.ReadToEnd();}
 static Dictionary<string,object> Json(string text){try{return new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(text);}catch(Exception){return null;}}
 static string StatusOf(string text,string fallback){var j=Json(text);object v;return j!=null&&j.TryGetValue("status",out v)&&v!=null?Convert.ToString(v):fallback;}
 static string Message(string text){var j=Json(text);object v;return j!=null&&j.TryGetValue("message",out v)&&v!=null?Convert.ToString(v):"거절됨";}

 static Dictionary<string,string> Load() {
  try{if(File.Exists(StateFile)){var d=new JavaScriptSerializer().Deserialize<Dictionary<string,string>>(File.ReadAllText(StateFile,Encoding.UTF8));if(d!=null)return d;}}
  catch(Exception){}
  return new Dictionary<string,string>();
 }
 static void Save(Dictionary<string,string> state) {
  try {
   Directory.CreateDirectory(Path.GetDirectoryName(StateFile));
   // Keep the newest entries only; the game keeps five automatic replays anyway.
   if(state.Count>2000){var keep=new Dictionary<string,string>();int skip=state.Count-1000;foreach(var kv in state){if(skip-->0)continue;keep[kv.Key]=kv.Value;}state.Clear();foreach(var kv in keep)state[kv.Key]=kv.Value;}
   string temp=StateFile+".tmp";File.WriteAllText(temp,new JavaScriptSerializer().Serialize(state),Encoding.UTF8);
   if(File.Exists(StateFile))File.Delete(StateFile);File.Move(temp,StateFile);
  } catch(IOException){} catch(UnauthorizedAccessException){}
 }
}
