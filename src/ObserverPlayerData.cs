using System;
using System.IO;
using System.Text;
using System.Drawing;

internal class ObserverPlayerRow {
 internal int Slot,Ki,Ore,PopulationUsed,PopulationCap,Workers;
 internal string Name,Faction;
 internal Color TeamColor;
 // Native 519D5D stores race at +35 (3=spectator). 51CF54/520ED1 use
 // RGB bytes +20..22. 51D100 formats population +3D/+43 xor 2002.
 // +39 is the resolved six-way faction (519D63), not the lobby alliance/team.
 // 4E39F0 maps POWER1/2 -> 2/3, TECH1/2 -> 0/1, MAGIC1/2 -> 4/5.
 internal static ObserverPlayerRow Read(Func<int,int,byte[]> read,int player,int slot,string savedName=null,Func<int,int> workerCount=null) {
  byte[] header=read(player+0x18,0x2d);if(header==null||header.Length!=0x2d)throw new IOException("참가자 정보 읽기 실패");
  int race=BitConverter.ToInt32(header,0x1d);if(race==3)return null;
  string[] factions={"촉나라","위나라","오나라"};
  string[] detailed={"촉제국","촉연합","위제국","위연합","오제국","오연합"};
  int faction=BitConverter.ToInt32(header,0x21);
  string factionName=faction>=0&&faction<6&&faction/2==race?detailed[faction]:(race>=0&&race<3?factions[race]:"진영 "+race);
  string name=savedName;
  if(String.IsNullOrEmpty(name)){byte[] raw=read(player+0x165a,41);if(raw==null)throw new IOException("참가자 이름 읽기 실패");int n=Array.IndexOf(raw,(byte)0);name=Encoding.GetEncoding(949).GetString(raw,0,n<0?raw.Length:n);}
  if(String.IsNullOrWhiteSpace(name)||name.IndexOfAny(new char[]{'\r','\n','\t'})>=0)name="플레이어 "+(slot+1);
  int ki=BitConverter.ToInt32(header,0x10)^0x36628020,ore=BitConverter.ToInt32(header,0x14)^0x36628020;
  if(ki<0||ore<0)return null;
  return new ObserverPlayerRow{Slot=slot,Name=name,Faction=factionName,Ki=ki,Ore=ore,Workers=workerCount==null?CountWorkers(read,player):workerCount(player),
   PopulationUsed=BitConverter.ToUInt16(header,0x25)^0x2002,PopulationCap=BitConverter.ToUInt16(header,0x2b)^0x2002,
   TeamColor=Color.FromArgb(header[8],header[9],header[10])};
 }
 // Native player list: head +4, count +8; node object +4, next +8.
 // Type getter 565810 reads WORD +4; dead getter 50BAD0 reads DWORD +67.
 // Traverse ownership lists rather than counting effect objects in INSTTBL.
 internal static int CountWorkers(Func<int,int,byte[]> read,int player) {
  byte[] list=read(player+4,8);if(list==null||list.Length!=8)return -1;
  int node=BitConverter.ToInt32(list,0),count=BitConverter.ToInt32(list,4),workers=0;
  if(count<0||count>16384)return -1;
  var seen=new System.Collections.Generic.HashSet<int>();
  for(int i=0;i<count;i++){
   if(node<=0||!seen.Add(node))return -1;
   byte[] link=read(node+4,8);if(link==null||link.Length!=8)return -1;
   int unit=BitConverter.ToInt32(link,0);node=BitConverter.ToInt32(link,4);
   if(unit<=0)return -1;
   byte[] data=read(unit,0x6b);if(data==null||data.Length!=0x6b)return -1;
   int type=BitConverter.ToUInt16(data,4);
   if((type==0x402||type==0x438||type==0x464)&&BitConverter.ToInt32(data,0x67)!=1)workers++;
  }
  return node==0?workers:-1;
 }
}

internal sealed class ObserverWorkerCounter {
 sealed class Entry {internal int Value;internal long At;}
 readonly System.Collections.Generic.Dictionary<int,Entry> cache=new System.Collections.Generic.Dictionary<int,Entry>();
 internal void Clear(){cache.Clear();}
 internal int Count(Func<int,int,byte[]> read,int player){
  long now=System.Diagnostics.Stopwatch.GetTimestamp();Entry entry;
  if(cache.TryGetValue(player,out entry)&&now-entry.At<System.Diagnostics.Stopwatch.Frequency)return entry.Value;
  int value=ObserverPlayerRow.CountWorkers(read,player);cache[player]=new Entry{Value=value,At=now};return value;
 }
}
