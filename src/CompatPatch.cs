using System;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;

// Private-service bootstrap. All account/lobby/room UI remains the original game UI.
static class CompatPatch {
 static void Put(byte[] b,int p,int x){Array.Copy(BitConverter.GetBytes(x),0,b,p,4);}
 internal static void Apply(string file,string ip) {
  IPAddress address;
  if(!IPAddress.TryParse(ip,out address)||address.AddressFamily!=AddressFamily.InterNetwork||address.Equals(IPAddress.Any)||address.Equals(IPAddress.Broadcast))throw new ArgumentException("호환 서버의 IPv4 주소를 입력하세요.");
  ip=address.ToString();byte[] b=File.ReadAllBytes(file);int pe=BitConverter.ToInt32(b,60),opt=pe+24;
  int section=opt+BitConverter.ToUInt16(b,pe+20)+(BitConverter.ToUInt16(b,pe+6)-1)*40;
  if(Encoding.ASCII.GetString(b,section,6)!=".rally"||BitConverter.ToInt32(b,section+8)!=0x1400||b[0x60ad9]!=0xe8||BitConverter.ToInt32(b,0x60ada)!=0x4f6460-0x460ade)throw new InvalidDataException("호환 서버 패치 대상 불일치");
  int raw=BitConverter.ToInt32(b,section+20);Array.Resize(ref b,raw+0x1600);
  Array.Copy(Encoding.ASCII.GetBytes(ip+"\0"),0,b,raw+0x1500,ip.Length+1);
  // Redirect every primary/fallback lobby address, without contacting the old service.
  foreach(int p in new[]{0x2bab6,0x2babd,0x2bad2})Put(b,p,0xb81500);
  using(var m=new MemoryStream())using(var w=new BinaryWriter(m)){
   foreach(int target in new[]{0x42b710,0x4f6b40,0x42bee0}){
    w.Write((byte)0xe8);w.Write(target-(0xb81400+(int)m.Position+4));
    w.Write(new byte[]{0x85,0xc0,0x0f,0x84});w.Write(0xb81460-(0xb81400+(int)m.Position+4));
   }
   w.Write(new byte[]{0x6a,0,0x6a,0x16,0xe8});w.Write(0x465b90-(0xb81400+(int)m.Position+4));
   w.Write(new byte[]{0x83,0xc4,8,0xe9});w.Write(0x460e82-(0xb81400+(int)m.Position+4));
   Array.Copy(m.ToArray(),0,b,raw+0x1400,m.Length);
  }
  using(var m=new MemoryStream())using(var w=new BinaryWriter(m)){
   w.Write(new byte[]{0xc7,5});w.Write(0x8517fc);w.Write(2);
   w.Write(new byte[]{0x6a,1,0x6a,0x33,0xe8});w.Write(0x465b90-(0xb81460+(int)m.Position+4));
   w.Write(new byte[]{0x83,0xc4,8,0xe9});w.Write(0x460e82-(0xb81460+(int)m.Position+4));
   Array.Copy(m.ToArray(),0,b,raw+0x1460,m.Length);
  }
  // The discontinued update/serial service is not needed by the private lobby.
  // This changes only Internet initialization, never single-player or game data.
  b[0x60ad9]=0xe9;Put(b,0x60ada,0xb81400-0x460ade);
  Put(b,section+8,0x1600);Put(b,section+16,0x1600);Put(b,opt+4,BitConverter.ToInt32(b,opt+4)+0x200);
  File.WriteAllBytes(file,b);
 }
}
