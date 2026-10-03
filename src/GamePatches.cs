using System;
using System.IO;
using System.Reflection;
using System.Security.Cryptography;

static class GamePatches {
 const string SupportedHash="A0EE96931B3B74FCE739062D8E58253892510EF863E9127648AC38FD4D515F99";
 static int U16(byte[] b,int o) {return BitConverter.ToUInt16(b,o);}
 static int U32(byte[] b,int o) {return BitConverter.ToInt32(b,o);}
 static void Put(byte[] b,int o,int n) {Array.Copy(BitConverter.GetBytes(n),0,b,o,4);}
 static int Align(int n,int a) {return checked((n+a-1)/a*a);}
 static void Hook(byte[] b,int offset,int target,byte[] expected) {
 for(int i=0;i<expected.Length;i++)if(b[offset+i]!=expected[i])throw new InvalidDataException("패치 대상 명령이 다릅니다.");
 b[offset]=0xe8;Put(b,offset+1,target-(0x400000+offset+5));for(int i=5;i<expected.Length;i++)b[offset+i]=0x90;
 }
 public static string Build(string original,string output) {
 if(string.Equals(Path.GetFullPath(original),Path.GetFullPath(output),StringComparison.OrdinalIgnoreCase))throw new InvalidDataException("원본과 패치 출력 경로는 달라야 합니다.");
 byte[] bytes=File.ReadAllBytes(original);string hash;
 using(var sha=SHA256.Create())hash=BitConverter.ToString(sha.ComputeHash(bytes)).Replace("-","");
 if(hash!=SupportedHash)throw new InvalidDataException("지원하는 원본 1.20g 실행 파일과 SHA256이 다릅니다. 게임 패치를 중단했습니다.");
 byte[] payload;using(var s=Assembly.GetExecutingAssembly().GetManifestResourceStream("rally.bin")){if(s==null)throw new Exception("게임 패치 리소스 누락");using(var m=new MemoryStream()){s.CopyTo(m);payload=m.ToArray();}}
 int pe=U32(bytes,60), optional=pe+24, count=U16(bytes,pe+6), table=optional+U16(bytes,pe+20), section=table+count*40;
 int sa=U32(bytes,optional+32),fa=U32(bytes,optional+36),end=0;
 for(int i=0;i<count;i++){int o=table+i*40;end=Math.Max(end,U32(bytes,o+12)+Math.Max(U32(bytes,o+8),U32(bytes,o+16)));}
 int rva=Align(end,sa),raw=Align(bytes.Length,fa),rawSize=Align(payload.Length,fa);
 if(rva!=0x780000||section+40>U32(bytes,optional+60))throw new InvalidDataException("PE 패치 섹션 구조 불일치");
 Array.Resize(ref bytes,raw+rawSize);Array.Copy(payload,0,bytes,raw,payload.Length);
 Array.Copy(System.Text.Encoding.ASCII.GetBytes(".rally"),0,bytes,section,6);Put(bytes,section+8,payload.Length);Put(bytes,section+12,rva);Put(bytes,section+16,rawSize);Put(bytes,section+20,raw);Put(bytes,section+36,unchecked((int)0xe0000020));
 Array.Copy(BitConverter.GetBytes((ushort)(count+1)),0,bytes,pe+6,2);Put(bytes,optional+4,U32(bytes,optional+4)+rawSize);Put(bytes,optional+56,Align(rva+payload.Length,sa));Put(bytes,optional+64,0);
 Hook(bytes,0x12c000,0xb80d00,new byte[]{0xe8,0x9b,0x77,0x04,0});
 Hook(bytes,0x117ac0,0xb80f00,new byte[]{0xa0,0xf8,0xd7,0x8c,0});bytes[0x117ac0]=0xe9;
 if(U32(bytes,0x12b5ae)!=0x52ad50||U32(bytes,0x12b632)!=0x52abb0)throw new InvalidDataException("F2 binding mismatch");
 Put(bytes,0x12b5ae,0xb80e00);Put(bytes,0x12b632,0xb80e00);
 Hook(bytes,0x659ba,0xb80c00,new byte[]{0xe8,0x41,0x11,0xfe,0xff});
 Hook(bytes,0xf5793,0xb80800,new byte[]{0xe8,0x88,0x9f,0xf5,0xff});
 Hook(bytes,0x130bb0,0xb80000,new byte[]{0xff,0x90,0xe8,1,0,0});
 Hook(bytes,0x12f3f0,0xb80000,new byte[]{0xff,0x90,0xe8,1,0,0});
 Hook(bytes,0x12f1f5,0xb80100,new byte[]{0xff,0x92,0xec,1,0,0});
 Hook(bytes,0xf5843,0xb80400,new byte[]{0xe8,0xa8,0xa6,0x05,0});
 Hook(bytes,0xf5887,0xb80400,new byte[]{0xe8,0x64,0xa6,0x05,0});
 Hook(bytes,0xf58bc,0xb80550,new byte[]{0xe8,0xdf,0x9c,0x05,0});
 Hook(bytes,0x118731,0xb80600,new byte[]{0xe8,0x4a,0x7c,0xfe,0xff});
 Hook(bytes,0x1664d0,0xb80700,new byte[]{0x56,0x8b,0xf1,0x8b,0x06});bytes[0x1664d0]=0xe9;
 using(var stream=Assembly.GetExecutingAssembly().GetManifestResourceStream("selection.bin")) {
 if(stream==null)throw new InvalidDataException("64 selection resource missing");
 using(var reader=new BinaryReader(stream)) {
 int total=reader.ReadInt32();for(int entry=0;entry<total;entry++) {
 int offset=reader.ReadInt32(),length=reader.ReadInt32();byte[] expected=reader.ReadBytes(length),replacement=reader.ReadBytes(length);
 for(int k=0;k<length;k++)if(bytes[offset+k]!=expected[k])throw new InvalidDataException("Selection patch mismatch: "+offset.ToString("X"));
 Array.Copy(replacement,0,bytes,offset,length);
 }}}
 string temp=output+".tmp";File.WriteAllBytes(temp,bytes);if(File.Exists(output))File.Delete(output);File.Move(temp,output);return output;
 }
}
