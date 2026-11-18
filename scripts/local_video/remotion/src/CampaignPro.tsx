import React from 'react';
import {AbsoluteFill,Composition,Img,Sequence,interpolate,staticFile,useCurrentFrame} from 'remotion';
import stories from '../campaign-pro.json';
const C={ink:'#142a32',paper:'#f4f6f5',blue:'#a7c7ce',gold:'#b99552'};
const A=(s:string)=>staticFile('campaign/'+s);
const clamp={extrapolateLeft:'clamp',extrapolateRight:'clamp'} as const;
const E=(f:number,d=0,n=22)=>1-Math.pow(1-interpolate(f,[d,d+n],[0,1],clamp),4);
type Shot=typeof stories[number]['scenes'][number];
type Story=typeof stories[number];
const image=(name:string,f:number)=>A(`${name}-frames/${String(Math.min(119,Math.max(0,Math.floor(f/2)))).padStart(3,'0')}.jpg`);
const Arrow=({color=C.ink,size=40}:{color?:string;size?:number})=><svg width={size} height={size} viewBox="0 0 40 40"><path d="M8 32L32 8M8 8h24v24" fill="none" stroke={color} strokeWidth="2.5"/></svg>;
const Type:React.FC<{s:Shot;light:boolean;center?:boolean}>=({s,light,center})=>{
 const f=useCurrentFrame();const longest=Math.max(...s.lines.map(x=>x.length));
 const size=Math.min(center?100:82,Math.floor(1040/Math.max(11,longest)));
 return <div style={{position:'absolute',left:48,right:44,top:center?300:185,zIndex:5}}>
 {s.lines.map((line,i)=><div key={i} style={{overflow:'hidden',paddingBottom:10,marginBottom:-7}}><div style={{fontSize:size,fontWeight:700,letterSpacing:-size*.052,lineHeight:1.07,color:i===s.lines.length-1&&!light?C.blue:undefined,transform:`translateY(${(1-E(f,i*3))*(i===0?12:110)}%) translateX(${f*.025}px)`}}>{line}</div></div>)}
 {s.label&&<div style={{marginTop:29,fontSize:23,lineHeight:1.45,maxWidth:560,opacity:E(f,8),transform:`translateY(${(1-E(f,8))*15}px)`}}>{s.label}</div>}
 </div>;
};
const Screen:React.FC<{file:string;mobile?:string;f:number;hero?:boolean;wide?:boolean}>=({file,mobile,f,hero,wide})=><div style={{position:'absolute',top:wide?570:610,left:wide?32:42,width:wide?656:636,height:hero?440:465,transform:`perspective(1800px) rotateY(${(-6+E(f,4)*8)}deg) rotateZ(${-3+E(f,4)*4}deg) translateY(${(1-E(f,4))*100-f*.12}px) scale(${.97+f*.0004})`}}>
 <div style={{height:'100%',overflow:'hidden',borderRadius:12,boxShadow:'0 40px 90px #06161d55',background:C.paper,border:'1px solid #ffffff40'}}>
 <div style={{height:30,background:'#e8eeeb',display:'flex',alignItems:'center',gap:5,paddingLeft:14}}>{[0,1,2].map(i=><span key={i} style={{width:5,height:5,background:'#82979a',borderRadius:9}}/>)}<span style={{fontSize:11,color:C.ink,marginLeft:20}}>{hero?'nienfos.com':'Diseño y desarrollo · Nienfos'}</span></div>
 <Img src={hero?image('hero',f):A(file)} style={{width:'100%',height:'calc(100% - 30px)',objectFit:'cover',objectPosition:'left top',transform:`scale(${1+f*.0003})`,transformOrigin:'center top'}}/>
 </div>
 {mobile&&<div style={{position:'absolute',right:55,top:210,width:174,height:345,border:'6px solid #12252b',borderRadius:26,overflow:'hidden',boxShadow:'0 25px 60px #0005',transform:`translateY(${(1-E(f,12))*120-f*.15}px) rotate(4deg)`}}><Img src={A(mobile)} style={{width:'100%',height:'100%',objectFit:'cover',objectPosition:'top'}}/></div>}
 </div>;
const Diagram:React.FC<{f:number;light:boolean;items:string[];network:boolean}>=({f,light,items,network})=>{
 const fg=light?C.ink:C.paper;const nodes=network?['Web','Gestión','Equipo','Datos']:items;
 return <div style={{position:'absolute',left:48,right:48,top:650,height:420}}>
 {network?<><svg width="624" height="420" style={{position:'absolute'}}>{[[70,60],[554,60],[70,350],[554,350]].map(([x,y],i)=><g key={i}><path d={`M312 205 Q${x} 205 ${x} ${y}`} fill="none" stroke={light?'#a4b8bb':'#547780'} strokeWidth="1.5"/><circle cx={312+(x-312)*((f/42+i*.2)%1)} cy={205+(y-205)*((f/42+i*.2)%1)} r="4" fill={C.blue}/></g>)}</svg><div style={{position:'absolute',left:246,top:139,width:132,height:132,borderRadius:'50%',border:'1px solid #a7c7ce',display:'grid',placeItems:'center',background:light?C.paper:C.ink,transform:`scale(${.9+E(f)*.1})`}}><Img src={A(light?'logo-primary.png':'logo-reverse.png')} style={{width:110,height:50,objectFit:'contain'}}/></div>{nodes.map((n,i)=><div key={n} style={{position:'absolute',left:i%2?450:0,top:i<2?24:312,width:174,height:70,borderBottom:`1px solid ${fg}55`,fontSize:26,display:'flex',alignItems:'center',justifyContent:'center',opacity:E(f,i*4)}}>{n}</div>)}</>:
 <>{nodes.map((n,i)=><div key={n} style={{display:'flex',alignItems:'center',gap:25,height:112,borderBottom:`1px solid ${fg}40`,transform:`translateX(${(1-E(f,7+i*5))*120}px)`,opacity:E(f,7+i*5)}}><span style={{fontSize:14,color:light?'#557079':C.blue}}>0{i+1}</span><span style={{fontSize:29,letterSpacing:-1,flex:1}}>{n}</span><div style={{transform:`rotate(${(1-E(f,12+i*5))*90}deg)`}}><Arrow color={fg} size={28}/></div></div>)}</>}
 </div>;
};
const ShotView:React.FC<{s:Shot;story:Story;index:number;count:number}>=({s,story,index,count})=>{
 const f=useCurrentFrame(),frames=Math.round(s.seconds*30);
 const light=Boolean(s.light)||s.layout==='close';const fg=light?C.ink:C.paper;
 const ocean=s.layout==='ocean',isType=s.layout==='type',close=s.layout==='close';
 const exit=interpolate(f,[frames-14,frames],[0,1],clamp);
 const reveal=index===0?1:E(f,0,15);
 return <AbsoluteFill style={{background:light?C.paper:C.ink,color:fg,overflow:'hidden',fontFamily:'Nienfos, sans-serif',clipPath:`inset(0 ${100-reveal*100}% 0 0)`}}>
 <style>{`@font-face{font-family:Nienfos;src:url('${A('NotoSans-Regular.ttf')}');font-weight:400}@font-face{font-family:Nienfos;src:url('${A('NotoSans-Bold.ttf')}');font-weight:700}*{box-sizing:border-box}`}</style>
 <AbsoluteFill style={{background:light?'radial-gradient(ellipse at 100% 70%,#d9e6e2,transparent 65%)':'radial-gradient(ellipse at 90% 65%,#31545f,transparent 68%)'}}/>
 {ocean&&<><Img src={image('ocean',f*1.4)} style={{position:'absolute',width:'100%',height:'100%',objectFit:'cover',objectPosition:'50% center',transform:`scale(${1.12+f*.001}) translateX(${-f*.09}px)`}}/><AbsoluteFill style={{background:'linear-gradient(180deg,#10252eef 0%,#10252eb0 38%,#10252e00 75%,#10252eaa)'}}/><div style={{position:'absolute',left:60-f*.8,top:650+Math.sin(f/30)*12,width:640,transform:`rotate(${-8+f*.035}deg)`}}><Img src={A('whale-original.svg')} style={{width:580}}/><Img src={A('whale-original.svg')} style={{position:'absolute',width:255,top:200,left:350}}/></div></>}
 {!ocean&&<svg width="720" height="1280" style={{position:'absolute',opacity:light?.18:.12}}>{[48,360,672].map(x=><path key={x} d={`M${x} 0V1280`} stroke={fg} strokeWidth=".6"/>)}<path d="M0 120H720M0 1160H720" stroke={fg} strokeWidth=".6"/></svg>}
 <AbsoluteFill style={{transform:`translateX(${-exit*28}px) scale(${1-exit*.018})`}}>
 <div style={{position:'absolute',left:48,right:48,top:66,display:'flex',justifyContent:'space-between',alignItems:'center',zIndex:10}}><span style={{fontSize:27,fontWeight:700,letterSpacing:-1}}>Nienfos<span style={{color:light?'#718f98':C.blue}}>.</span></span><span style={{fontSize:12,letterSpacing:2.3}}>{close?'HABLEMOS':'DISEÑO + DESARROLLO'}</span></div>
 <Type s={s} light={light} center={isType}/>
 {isType&&<><div style={{position:'absolute',left:38,top:740,fontSize:190,fontWeight:700,lineHeight:1,letterSpacing:-13,color:'transparent',WebkitTextStroke:`1px ${fg}50`,transform:`translateX(${40-f*1.1}px)`}}>{story.id==='07'?'Proyectos.':story.id==='05'?'Con vos.':'A medida.'}</div><div style={{position:'absolute',left:48,top:1015,width:92+E(f,8)*445,height:1,background:fg,opacity:.5}}/><div style={{position:'absolute',right:52,top:1000,transform:`translateX(${(1-E(f,8))*-100}px)`}}><Arrow color={fg} size={32}/></div></>}
 {s.layout==='hero'&&<Screen file="" f={f} hero wide/>}
 {(s.layout==='browser'||s.layout==='portfolio')&&<Screen file={s.asset!} mobile={s.mobile} f={f} wide={s.layout==='portfolio'}/>}
 {['tiles','stack','services','flow','split','network'].includes(s.layout)&&<Diagram f={f} light={light} network={s.layout==='network'} items={s.items||['Webs y catálogos','Software a medida','Integración y automatización']}/>}
 {['step','service'].includes(s.layout)&&<><div style={{position:'absolute',left:28,top:640,fontSize:310,fontWeight:700,lineHeight:1,letterSpacing:-24,color:'transparent',WebkitTextStroke:`1.3px ${light?'#7f9ea7':C.blue}`,transform:`translateY(${(1-E(f,4))*100}px) translateX(${-f*.13}px)`}}>{s.number}</div><div style={{position:'absolute',left:48,top:1020,right:48,height:1,background:fg,transform:`scaleX(${E(f,8)})`,transformOrigin:'left'}}/><div style={{position:'absolute',right:65,top:860,transform:`rotate(${-45+E(f,7)*45}deg)`}}><Arrow size={75} color={fg}/></div></>}
 {s.layout==='duo'&&<><div style={{position:'absolute',left:45,top:625,width:530,height:285,overflow:'hidden',boxShadow:'0 30px 70px #0005',transform:`rotate(-5deg) translateX(${(1-E(f,4))*-200-f*.2}px)`}}><Img src={A('chrem-web.webp')} style={{width:'100%'}}/></div><div style={{position:'absolute',left:170,top:860,width:510,height:270,overflow:'hidden',boxShadow:'0 30px 70px #0005',transform:`rotate(4deg) translateX(${(1-E(f,10))*200+f*.1}px)`}}><Img src={A('rd-access.webp')} style={{width:'100%'}}/></div></>}
 {close&&<><div style={{position:'absolute',top:660,left:48,right:48,borderTop:'1px solid #9bafaf',paddingTop:45,transform:`translateY(${(1-E(f,7))*45}px)`}}><Img src={A('logo-primary.png')} style={{width:490,height:160,objectFit:'contain',objectPosition:'left'}}/></div><div style={{position:'absolute',left:48,right:48,top:1030,display:'flex',alignItems:'center',justifyContent:'space-between',fontSize:34,letterSpacing:-1}}><span>nienfos.com</span><div style={{width:72,height:72,borderRadius:'50%',border:'1px solid #7f9ea7',display:'grid',placeItems:'center',transform:`rotate(${-30+E(f,8)*30}deg)`}}><Arrow/></div></div></>}
 <div style={{position:'absolute',left:48,right:48,bottom:66,display:'flex',justifyContent:'space-between',fontSize:12,letterSpacing:1.7,opacity:.75}}><span>{ocean?'UNA IDENTIDAD PROPIA':'WEB · SOFTWARE · INTEGRACIÓN'}</span><span>{String(index+1).padStart(2,'0')} / {String(count).padStart(2,'0')}</span></div>
 </AbsoluteFill>
 </AbsoluteFill>;
};
const Film:React.FC<{story:Story}>=({story})=>{
 let t=0;const frame=useCurrentFrame();const total=story.scenes.reduce((n,s)=>n+Math.round(s.seconds*30),0);
 return <AbsoluteFill style={{background:C.ink}}>{story.scenes.map((s,i)=>{const start=t;const n=Math.round(s.seconds*30);t+=n;return <Sequence key={i} from={start} durationInFrames={n+(i<story.scenes.length-1?16:0)}><ShotView s={s} story={story} index={i} count={story.scenes.length}/></Sequence>})}<div style={{position:'absolute',bottom:0,height:3,left:0,width:`${100*frame/(total-1)}%`,background:C.gold}}/></AbsoluteFill>
};
export const CampaignProRoots=()=> <>{stories.map(story=><Composition key={story.id} id={'NienfosPro-'+story.id} component={Film} defaultProps={{story}} durationInFrames={story.scenes.reduce((n,s)=>n+Math.round(s.seconds*30),0)} width={720} height={1280} fps={30}/>)}</>;
