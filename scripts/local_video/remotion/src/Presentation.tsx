import React from 'react';
import {AbsoluteFill,Composition,Img,Sequence,interpolate,staticFile,useCurrentFrame} from 'remotion';
const A=(s:string)=>staticFile('campaign/'+s);
const ink='#142a32',paper='#f4f6f5',blue='#a7c7ce';
const clamp={extrapolateLeft:'clamp',extrapolateRight:'clamp'} as const;
const e=(f:number,d=0,n=24)=>1-Math.pow(1-interpolate(f,[d,d+n],[0,1],clamp),4);
export const presentationScenes=[
 {title:['Esto es','Nienfos.'],label:'Webs y software para tu negocio',kind:'intro',light:false,frames:90},
 {title:['Primero,','te escuchamos.'],label:'Entendemos tu negocio y definimos el alcance.',kind:'listen',light:true,frames:105},
 {title:['Le damos forma.','Con vos.'],label:'Diseñamos, compartimos y ajustamos.',kind:'design',light:false,frames:105},
 {title:['Cada parte,','conectada.'],label:'Desarrollamos, probamos y mejoramos.',kind:'build',light:true,frames:105},
 {title:['Ideas que ya','son proyectos.'],label:'Chrem Propiedades · Consultora RD',kind:'clients',light:false,frames:105},
 {title:['Contanos qué','tenés en mente.'],label:'Diseño. Desarrollo. Acompañamiento.',kind:'close',light:true,frames:90},
];
// A continuous geometric field: the scene changes, the same space keeps moving.
const Field:React.FC<{time:number;light:boolean}>=({time,light})=><AbsoluteFill style={{overflow:'hidden',background:light?paper:ink}}>
 <AbsoluteFill style={{background:light?'radial-gradient(ellipse at 90% 65%,#d7e5e0,transparent 65%)':'radial-gradient(ellipse at 80% 65%,#365967,transparent 75%)'}}/>
 {[{x:365,y:410,w:300,h:300},{x:40,y:710,w:245,h:335},{x:395,y:840,w:250,h:190},{x:545,y:135,w:240,h:240},{x:-120,y:360,w:220,h:170},{x:310,y:1090,w:335,h:220}].map((t,i)=>{
 const dx=Math.sin(time/52+i*1.2)*40,dy=Math.cos(time/63+i*.9)*38;
 return <div key={i} style={{position:'absolute',left:t.x+dx,top:t.y+dy,width:t.w,height:t.h,borderRadius:12,border:`1px solid ${light?'#829eaa45':'#b1d2db35'}`,background:light?(i%2?'#9ebbb51a':'#ffffff42'):(i%2?'#85b8ca12':'#a7c7ce0b'),transform:`perspective(1600px) rotate(${Math.sin(time/100+i)*7}deg) rotateY(${Math.sin(time/80+i)*12}deg) scale(${1+Math.sin(time/70+i)*.06})`}}/>;
 })}
 <svg width="720" height="1280" style={{position:'absolute',opacity:light?.17:.12}}><path d="M48 0V1280M672 0V1280M0 120H720M0 1160H720" stroke={light?ink:paper} strokeWidth=".7"/></svg>
 </AbsoluteFill>;
const Window:React.FC<{file:string;width:number;height:number;label:string}>=({file,width,height,label})=><div style={{width,height,background:paper,border:'1px solid #ffffff66',borderRadius:9,overflow:'hidden',boxShadow:'0 20px 50px #051c2840'}}><div style={{height:26,background:'#e4ebe7',display:'flex',alignItems:'center',gap:5,paddingLeft:11}}>{[0,1,2].map(i=><span key={i} style={{width:4,height:4,borderRadius:5,background:'#8ba2aa'}}/>)}<span style={{fontSize:9,color:ink,marginLeft:13}}>{label}</span></div><Img src={A(file)} style={{width:'100%',height:height-26,objectFit:'cover',objectPosition:'left top'}}/></div>;
const Workflow:React.FC<{kind:string;f:number;light:boolean}>=({kind,f,light})=>{
 const fg=light?ink:paper;
 if(kind==='listen')return <div style={{position:'absolute',left:48,top:660,width:624,height:390}}>
 {['Tu negocio','Tus necesidades','El próximo paso'].map((s,i)=>{const q=e(f,10+i*7,35);return <div key={s} style={{position:'absolute',left:30+i*25,top:i*106,width:550,height:88,borderRadius:9,border:'1px solid #7f9ea780',background:'#f4f6f5dd',display:'flex',alignItems:'center',padding:'0 24px',gap:22,fontSize:25,transform:`translateX(${(1-q)*(i%2?-220:220)}px) rotate(${(1-q)*(i%2?-12:12)}deg)`,opacity:q}}><span style={{fontSize:13,color:'#63848e'}}>0{i+1}</span>{s}<span style={{marginLeft:'auto',opacity:e(f,45+i*6)}}>✓</span></div>})}</div>;
 if(kind==='design')return <div style={{position:'absolute',left:65,top:610,width:590,height:430,padding:24,border:'1px solid #a7c7ce88',borderRadius:12,background:'#1b3540d9',transform:`perspective(1500px) rotateY(${-8+e(f,5)*12}deg) translateY(${(1-e(f,5))*55}px)`}}>
 <div style={{height:22,borderBottom:'1px solid #7f9ea760',display:'flex',gap:8}}>{[0,1,2].map(i=><span key={i} style={{width:5,height:5,background:blue,borderRadius:5}}/>)}</div>
 <div style={{width:180,height:14,background:blue,marginTop:36,transform:`scaleX(${e(f,12)})`,transformOrigin:'left'}}/>
 {[240,200].map((w,i)=><div key={i} style={{width:w,height:8,background:'#7f9ea7',marginTop:13,opacity:e(f,17+i*4)}}/>)}
 <div style={{display:'flex',gap:15,marginTop:35}}>{[0,1,2].map(i=><div key={i} style={{flex:1,height:150,border:'1px solid #7f9ea7',borderRadius:7,background:i===1?'#7f9ea733':'transparent',transform:`translateY(${(1-e(f,25+i*7))*80}px)`,opacity:e(f,25+i*7)}}><div style={{height:70,margin:12,borderRadius:4,background:'#a7c7ce25'}}/><div style={{height:6,margin:'16px 12px',background:'#a7c7ce88'}}/></div>)}</div>
 <div style={{position:'absolute',left:interpolate(f,[30,75],[400,290],clamp),top:interpolate(f,[30,75],[370,260],clamp),opacity:e(f,25)}}><svg width="35" height="44" viewBox="0 0 35 44"><path d="M2 2L30 24L18 26L13 40Z" fill={paper} stroke={ink} strokeWidth="2"/></svg></div>
 </div>;
 return <div style={{position:'absolute',left:48,top:650,width:624,height:420}}>
 <svg width="624" height="420" style={{position:'absolute'}}>{[0,1,2].map((n)=>{const x=100+n*210;const q=e(f,10+n*8,40);return <g key={n}><path d={`M${x} 80V210H312V320`} fill="none" stroke="#7f9ea7" strokeWidth="2" strokeDasharray="550" strokeDashoffset={550*(1-q)}/><circle cx={x+(312-x)*((f/70+n*.3)%1)} cy={210} r="4" fill={ink} opacity={e(f,35)}/></g>})}</svg>
 {['Web','Gestión','Herramientas'].map((s,i)=><div key={s} style={{position:'absolute',left:17+i*210,top:18,width:170,height:100,background:'#f4f6f5ee',border:'1px solid #7f9ea7',borderRadius:11,display:'grid',placeItems:'center',fontSize:23,opacity:e(f,6+i*7),transform:`translateY(${(1-e(f,6+i*7))*-80}px)`}}>{s}</div>)}
 <div style={{position:'absolute',left:175,top:280,width:274,height:96,background:ink,color:paper,borderRadius:12,display:'flex',alignItems:'center',justifyContent:'center',gap:15,fontSize:24,transform:`scale(${.85+e(f,35)*.15})`,opacity:e(f,35)}}>Una solución <span style={{color:blue}}>✓</span></div>
 </div>;
};
const Shot:React.FC<{index:number;start:number}>=({index,start})=>{
 const f=useCurrentFrame(),s=presentationScenes[index],fg=s.light?ink:paper;
 const reveal=index===0?1:e(f,0,16);
 return <AbsoluteFill style={{color:fg,fontFamily:'Nienfos, sans-serif',clipPath:`inset(0 ${100-reveal*100}% 0 0)`,overflow:'hidden'}}>
 <Field time={start+f} light={s.light}/>
 <div style={{position:'absolute',left:48,right:48,top:66,display:'flex',justifyContent:'space-between',alignItems:'center'}}><span style={{fontSize:27,fontWeight:700,letterSpacing:-1}}>Nienfos.</span><span style={{fontSize:12,letterSpacing:2}}>{s.kind==='close'?'HABLEMOS':'DISEÑO + DESARROLLO'}</span></div>
 <div style={{position:'absolute',left:48,right:44,top:190}}>{s.title.map((line,i)=><div key={line} style={{overflow:'hidden',paddingBottom:12,marginBottom:-8}}><div style={{fontSize:Math.min(82,Math.floor(1080/Math.max(13,...s.title.map(x=>x.length)))),fontWeight:700,letterSpacing:-3.5,lineHeight:1.1,color:!s.light&&i===1?blue:fg,transform:`translateY(${(1-e(f,i*4))*(i===0?10:105)}%)`}}>{line}</div></div>)}<div style={{fontSize:23,lineHeight:1.5,marginTop:28,maxWidth:575,opacity:e(f,10)}}>{s.label}</div></div>
 {s.kind==='intro'&&<div style={{position:'absolute',left:52,top:600,transform:`perspective(1600px) rotateY(${-8+e(f)*12}deg) rotateZ(${-3+e(f)*4}deg) translateY(${(1-e(f))*60-f*.15}px)`}}><Window file={`hero-frames/${String(Math.min(119,Math.floor(f/2))).padStart(3,'0')}.jpg`} width={616} height={412} label="nienfos.com"/></div>}
 {['listen','design','build'].includes(s.kind)&&<Workflow kind={s.kind} f={f} light={s.light}/>}
 {s.kind==='clients'&&<div style={{position:'absolute',left:48,right:48,top:690,display:'flex',gap:24}}>{[{file:'chrem-web.webp',label:'Chrem Propiedades'},{file:'rd-access.webp',label:'Consultora RD'}].map((c,i)=><div key={c.file} style={{transform:`translateY(${(1-e(f,8+i*8))*110+Math.sin(f/35+i)*9}px) rotate(${(i?2:-2)+Math.sin(f/60+i)}deg)`,opacity:e(f,8+i*8)}}><Window file={c.file} width={300} height={226} label={c.label}/><div style={{fontSize:20,marginTop:24,letterSpacing:-.4}}>{c.label}</div><div style={{fontSize:14,color:blue,marginTop:8}}>{i?'Plataforma de gestión':'Web y catálogo'}</div></div>)}</div>}
 {s.kind==='close'&&<><div style={{position:'absolute',left:48,right:48,top:660,borderTop:'1px solid #9bafaf',paddingTop:45,transform:`translateY(${(1-e(f,7))*45}px)`}}><Img src={A('logo-primary.png')} style={{width:490,height:160,objectFit:'contain',objectPosition:'left'}}/></div><div style={{position:'absolute',left:48,right:48,top:1030,display:'flex',alignItems:'center',justifyContent:'space-between',fontSize:34,letterSpacing:-1}}><span>nienfos.com</span><span style={{fontSize:55,transform:`rotate(${-35+e(f,7)*35}deg)`}}>↗</span></div></>}
 <div style={{position:'absolute',left:48,right:48,bottom:66,display:'flex',justifyContent:'space-between',fontSize:12,letterSpacing:1.5,opacity:.7}}><span>{['listen','design','build'].includes(s.kind)?'ASÍ TRABAJAMOS':'WEB · SOFTWARE · INTEGRACIÓN'}</span><span>{String(index+1).padStart(2,'0')} / 06</span></div>
 </AbsoluteFill>;
};
const Presentation=()=>{let t=0;return <AbsoluteFill style={{background:ink}}><style>{`@font-face{font-family:Nienfos;src:url('${A('NotoSans-Regular.ttf')}');font-weight:400}@font-face{font-family:Nienfos;src:url('${A('NotoSans-Bold.ttf')}');font-weight:700}*{box-sizing:border-box}`}</style>{presentationScenes.map((s,i)=>{const start=t;t+=s.frames;return <Sequence key={i} from={start} durationInFrames={s.frames+(i<5?17:0)}><Shot index={i} start={start}/></Sequence>})}</AbsoluteFill>};
export const PresentationRoot=()=> <Composition id="NienfosPresentacionV3" component={Presentation} durationInFrames={600} fps={30} width={720} height={1280}/>;
