import React from 'react';
import {AbsoluteFill,Composition,Img,Sequence,interpolate,staticFile,useCurrentFrame} from 'remotion';
const C={ink:'#142a32',paper:'#f4f6f5',blue:'#a7c7ce',gold:'#b99552'};
const A=(s:string)=>staticFile('campaign/'+s),D=(s:string)=>staticFile('presentation-v11/'+s);
const clamp={extrapolateLeft:'clamp',extrapolateRight:'clamp'} as const;
const e=(f:number,d=0,n=24)=>1-Math.pow(1-interpolate(f,[d,d+n],[0,1],clamp),4);
export const scenesV13=[
 {start:0,frames:113,kind:'intro',light:false,title:['Esto es','Nienfos.'],label:'Webs y software para tu negocio'},
 {start:113,frames:135,kind:'listen',light:true,title:['Entender primero.','Decidir mejor.'],label:'Escuchamos lo que necesitás.'},
 {start:248,frames:141,kind:'design',light:false,title:['Verlo. Probarlo.','Mejorarlo.'],label:'Revisás los avances con nosotros.'},
 {start:389,frames:145,kind:'build',light:true,title:['Conectar para','simplificar.'],label:'Integramos las herramientas que ya usás.'},
 {start:534,frames:90,kind:'close',light:true,title:['Contanos qué','tenés en mente.'],label:'Diseño. Desarrollo. Acompañamiento.'},
];
const Background:React.FC<{light:boolean;time:number}>=({light,time})=><AbsoluteFill style={{background:light?C.paper:C.ink}}>
 <AbsoluteFill style={{background:light?'radial-gradient(ellipse at 90% 70%,#dfeae4,transparent 70%)':'radial-gradient(ellipse at 90% 70%,#2c4d59,transparent 75%)'}}/>
 <svg width="720" height="1280" style={{position:'absolute'}}>{Array.from({length:7},(_,i)=><path key={'v'+i} d={`M${48+104*i} 0V1380`} stroke={light?C.ink:C.blue} strokeOpacity=".055" strokeWidth=".65"/>)}{Array.from({length:13},(_,i)=><path key={'h'+i} d={`M0 ${16+104*i}H720`} stroke={light?C.ink:C.blue} strokeOpacity=".055" strokeWidth=".65"/>)}{[{x:464,y:536},{x:152,y:848},{x:360,y:224}].map((c,i)=><rect key={i} {...c} width="104" height="104" fill={light?C.ink:C.blue} opacity={.012+(1+Math.sin(time/60+i))* .009}/>)}</svg>
 </AbsoluteFill>;
const Browser:React.FC<{f:number;wire?:boolean}>=({f,wire=false})=>{
 const reveal=wire?e(f,65,26):1;
 return <div style={{position:'absolute',left:0,top:25,width:610,height:435,borderRadius:12,background:C.paper,overflow:'hidden',boxShadow:'0 30px 80px #06161d40',border:'1px solid #ffffff50',transform:`perspective(1600px) rotateY(${-7+e(f,3)*10}deg) rotateZ(${-2+e(f,3)*3}deg) translateY(${(1-e(f,3))*75-f*.06}px)`}}>
 <div style={{height:30,background:'#e3eae6',display:'flex',gap:5,alignItems:'center',padding:'0 13px'}}>{[0,1,2].map(i=><span key={i} style={{width:5,height:5,borderRadius:6,background:'#8ca3a9'}}/>)}<span style={{fontSize:11,color:C.ink,marginLeft:20}}>nienfos.com</span></div>
 {wire&&<div style={{position:'absolute',inset:'30px 0 0',padding:25,background:'#edf2ef',color:C.ink}}><div style={{height:12,width:115,background:'#94b0b6',opacity:e(f,6)}}/><div style={{display:'flex',gap:24,marginTop:38}}><div style={{width:'55%'}}>{[90,75,55].map((w,i)=><div key={i} style={{height:17,width:w+'%',marginBottom:13,background:i===0?'#668993':'#b6c8c9',transform:`scaleX(${e(f,10+i*5)})`,transformOrigin:'left'}}/>)}<div style={{height:8,width:'85%',background:'#ccd8d4',marginTop:22}}/><div style={{height:8,width:'72%',background:'#ccd8d4',marginTop:12}}/><div style={{height:30,width:105,background:'#7f9ea7',marginTop:26,borderRadius:5,opacity:e(f,28)}}/></div><div style={{flex:1,height:165,border:'1px solid #93aeb5',borderRadius:8,background:'#d2dfdb',transform:`scale(${.8+e(f,20)*.2})`}}/></div><div style={{display:'flex',gap:15,marginTop:30}}>{[0,1,2].map(i=><div key={i} style={{flex:1,height:68,border:'1px solid #b2c5c6',background:'#e0e9e4',borderRadius:6,opacity:e(f,26+i*5)}}/>)}</div></div>}
 <div style={{position:'absolute',left:0,right:0,top:30,bottom:0,clipPath:`inset(0 ${100-reveal*100}% 0 0)`}}><Img src={D('desktop.png')} style={{width:'100%',height:'100%',objectFit:'cover',objectPosition:'top',transform:`scale(${1+f*.00015})`,transformOrigin:'center top'}}/></div>
 </div>;
};
// Alcance: a planning board, distinct from the later integration network.
const Discovery:React.FC<{f:number}>=({f})=>{
 const move=(start:number)=>e(f,start,26);
 const items=[
  {text:'Tu necesidad',tag:'OBJETIVO',y:115,delay:5,step:24,final:80,color:'#e0eae5'},
  {text:'Tu forma de trabajar',tag:'PROCESO',y:231,delay:12,step:40,final:89,color:'#e7ece8'},
  {text:'Tu equipo',tag:'PERSONAS',y:347,delay:19,step:56,final:98,color:'#dbe7e6'},
 ];
 return <div style={{position:'absolute',left:48,top:530,width:624,height:570}}>
 <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',paddingBottom:21,borderBottom:'1px solid #a7bec2'}}><span style={{fontSize:12,letterSpacing:2,color:'#516e78'}}>DE LA CONVERSACIÓN AL PLAN</span><span style={{fontSize:16,color:'#516e78'}}>01 — 03</span></div>
 {[{t:'Necesidades',n:'01'},{t:'Priorizamos',n:'02'},{t:'Acordamos',n:'03'}].map((c,i)=><div key={c.t} style={{position:'absolute',left:i*212,top:65,width:200,height:415,borderRadius:12,background:i===2?'#d9e5e340':'#142a3204',border:'1px solid #a7bec245'}}><div style={{display:'flex',alignItems:'center',gap:8,padding:'16px 10px',fontSize:18,fontWeight:700,letterSpacing:-.5}}><span style={{width:6,height:6,borderRadius:5,background:i===2?C.gold:'#799ca6'}}/>{c.t}</div><div style={{height:1,margin:'0 10px',background:'#a7bec260'}}/></div>)}
 {items.map((it,i)=>{
  const p=move(it.step),q=move(it.final),x=12+212*p+212*q;
  const moving=(p>0&&p<.995)||(q>0&&q<.995);
  return <div key={it.text} style={{position:'absolute',left:x,top:it.y-Math.sin(p*Math.PI)*14-Math.sin(q*Math.PI)*14,width:176,height:94,padding:'13px 12px',borderRadius:7,background:it.color,border:'1px solid #a4b9b6',borderTop:'3px solid #7b9e9e',boxShadow:moving?'0 15px 25px #142a3220':'0 3px 6px #142a3208',opacity:e(f,it.delay,15),transform:`translateY(${(1-e(f,it.delay,15))*30}px) rotate(${Math.sin(p*Math.PI)*-3+Math.sin(q*Math.PI)*2}deg)`}}><div style={{fontSize:9,letterSpacing:1.5,color:'#5a777c',marginBottom:9}}>{it.tag}<span style={{float:'right',opacity:q}}>✓</span></div><div style={{fontSize:i===1?18:21,fontWeight:700,lineHeight:1.15,letterSpacing:-.5}}>{it.text}</div></div>;
 })}
 <div style={{position:'absolute',left:0,right:0,top:505,display:'flex',alignItems:'center',justifyContent:'space-between',padding:'16px 19px',borderRadius:9,background:C.ink,color:C.paper,opacity:e(f,94,18),transform:`translateY(${(1-e(f,94,18))*16}px)`}}><span style={{fontSize:25,fontWeight:700,letterSpacing:-.7}}>Un alcance claro</span><span style={{fontSize:17,color:C.blue}}>Un plan compartido <span style={{marginLeft:14}}>✓</span></span></div>
 </div>;
};
const Design:React.FC<{f:number}>=({f})=><div style={{position:'absolute',left:45,top:540,width:630,height:550}}>
 <Browser f={f} wire/>
 <div style={{position:'absolute',left:365,top:175,width:225,height:66,borderRadius:'14px 14px 0 14px',background:C.blue,color:C.ink,padding:'20px',fontSize:20,opacity:e(f,38)*(1-e(f,85)),transform:`translateY(${(1-e(f,38))*28}px)`}}>Tu devolución ↗</div>
 <div style={{position:'absolute',left:interpolate(f,[30,60],[200,400],clamp),top:interpolate(f,[30,60],[360,270],clamp),opacity:e(f,26)*(1-e(f,75)),zIndex:6}}><svg width="32" height="42" viewBox="0 0 32 42"><path d="M2 2L29 24L18 26L13 39Z" fill={C.paper} stroke={C.ink} strokeWidth="2"/></svg></div>
 <div style={{position:'absolute',right:0,top:255,width:157,height:300,border:'6px solid #152b33',borderRadius:24,overflow:'hidden',background:C.ink,boxShadow:'0 20px 45px #0004',opacity:e(f,65),transform:`translateX(${(1-e(f,65))*140}px) rotate(${3+Math.sin(f/35)}deg)`}}><Img src={D('mobile.png')} style={{width:'100%',height:'100%',objectFit:'cover',objectPosition:'top'}}/></div>
 <div style={{position:'absolute',left:0,top:490,fontSize:22,color:C.blue,opacity:e(f,94)}}>Diseño que se prueba y evoluciona. <span>✓</span></div>
 </div>;
const Integration:React.FC<{f:number}>=({f})=>{
 const nodes=[{x:0,y:15,t:'Tu web',d:8},{x:450,y:85,t:'Gestión',d:22},{x:0,y:360,t:'Herramientas',d:36},{x:430,y:390,t:'Tu equipo',d:50}];
 return <div style={{position:'absolute',left:48,top:535,width:624,height:555}}>
 <svg width="624" height="550" style={{position:'absolute'}}>{nodes.map((n,i)=>{
 const x=n.x+83,y=n.y+44;const q=e(f,25+i*9,30),u=Math.max(0,((f-42-i*6)/47)%1);
 return <g key={i}><path d={`M${x} ${y} Q312 ${y} 312 260`} fill="none" stroke="#7f9ea7" strokeWidth="1.6" pathLength="1" strokeDasharray="1" strokeDashoffset={1-q}/><circle cx={(1-u)*(1-u)*x+2*(1-u)*u*312+u*u*312} cy={(1-u)*(1-u)*y+2*(1-u)*u*y+u*u*260} r="4" fill="#456f7e" opacity={q}/></g>;
 })}</svg>
 {nodes.map((n,i)=><div key={n.t} style={{position:'absolute',left:n.x,top:n.y,width:166,height:92,background:'#f8faf8',border:'1px solid #a7bec2',borderRadius:i%2?14:8,display:'grid',placeItems:'center',fontSize:22,opacity:e(f,n.d),transform:`translate(${(1-e(f,n.d))*(i%2?100:-100)}px,${(1-e(f,n.d))*20}px)`}}>{n.t}</div>)}
 <div style={{position:'absolute',left:209,top:157,width:206,height:206,borderRadius:32,background:C.ink,color:C.paper,display:'flex',flexDirection:'column',alignItems:'center',justifyContent:'center',boxShadow:'0 20px 45px #142a3220',transform:`rotate(${-8+e(f,16)*8}deg) scale(${.85+e(f,16)*.15})`}}><Img src={A('logo-reverse.png')} style={{width:155,height:58,objectFit:'contain'}}/><span style={{fontSize:20,color:C.blue,marginTop:18,opacity:e(f,57)}}>Conectamos</span><span style={{position:'absolute',right:-13,top:-13,width:40,height:40,borderRadius:'50%',display:'grid',placeItems:'center',background:C.blue,color:C.ink,fontSize:25,transform:`scale(${e(f,94,10)})`}}>✓</span></div>
 <div style={{position:'absolute',top:512,left:0,right:0,textAlign:'center',fontSize:23,fontWeight:700,letterSpacing:-.5,opacity:e(f,94)}}>La información fluye. El trabajo se simplifica.</div>
 </div>;
};
const Closing:React.FC<{f:number}>=({f})=><>
 <div style={{position:'absolute',left:48,right:48,top:590,height:270,borderTop:'1px solid #91a9af',paddingTop:45,transform:`translateY(${(1-e(f,8,27))*60}px)`,opacity:e(f,8,27)}}><Img src={A('logo-primary.png')} style={{width:490,height:160,objectFit:'contain',objectPosition:'left'}}/></div>
 <div style={{position:'absolute',left:48,right:48,top:930,display:'flex',alignItems:'center',justifyContent:'space-between',fontSize:39,letterSpacing:-1,opacity:e(f,22,22),transform:`translateY(${(1-e(f,22,22))*25}px)`}}><span>nienfos.com<div style={{height:1,marginTop:17,background:'#7f9ea7',transform:`scaleX(${e(f,48,18)})`,transformOrigin:'left'}}/></span><div style={{width:76,height:76,border:'1px solid #829fa7',borderRadius:'50%',display:'grid',placeItems:'center',fontSize:50,transform:`rotate(${-35+e(f,48,18)*35}deg)`}}>↗</div></div>
 <div style={{position:'absolute',left:48,top:1090,fontSize:17,color:'#516e78',letterSpacing:.3,opacity:e(f,45,20)}}>Una conversación puede ser el próximo paso.</div>
 </>;
const Shot:React.FC<{i:number}>=({i})=>{
 const f=useCurrentFrame(),s=scenesV13[i],fg=s.light?C.ink:C.paper;
 return <AbsoluteFill style={{color:fg,overflow:'hidden',clipPath:`inset(0 ${i===0?0:100-e(f,0,16)*100}% 0 0)`}}>
 <Background light={s.light} time={s.start+f}/>
 <div style={{position:'absolute',left:48,right:48,top:66,display:'flex',justifyContent:'space-between',alignItems:'center'}}><span style={{fontSize:27,fontWeight:700,letterSpacing:-1}}>Nienfos.</span><span style={{fontSize:12,letterSpacing:2}}>{s.kind==='close'?'HABLEMOS':'DISEÑO + DESARROLLO'}</span></div>
 <div style={{position:'absolute',left:48,right:44,top:190}}>{s.title.map((line,k)=><div key={line} style={{overflow:'hidden',paddingBottom:12,marginBottom:-8}}><div style={{fontSize:Math.min(82,Math.floor(1080/Math.max(13,...s.title.map(t=>t.length)))),fontWeight:700,letterSpacing:-3.5,lineHeight:1.1,color:!s.light&&k===1?C.blue:fg,transform:`translateY(${(1-e(f,k*4))*(k===0?10:105)}%)`}}>{line}</div></div>)}<div style={{fontSize:23,lineHeight:1.5,marginTop:28,maxWidth:575,opacity:e(f,10)}}>{s.label}</div></div>
 {s.kind==='intro'&&<div style={{position:'absolute',left:52,top:530,width:616,height:560}}><Browser f={f}/><div style={{position:'absolute',left:0,top:505,fontSize:18,color:C.blue,letterSpacing:.5,whiteSpace:'nowrap',opacity:e(f,30)}}>De la idea a lo que sigue.</div></div>}
 {s.kind==='listen'&&<Discovery f={f}/>}
 {s.kind==='design'&&<Design f={f}/>}
 {s.kind==='build'&&<Integration f={f}/>}
 {s.kind==='close'&&<Closing f={f}/>}
 <div style={{position:'absolute',left:48,right:48,bottom:66,display:'flex',justifyContent:'space-between',fontSize:12,letterSpacing:1.4,opacity:.7}}><span>{['listen','design','build'].includes(s.kind)?'ENTENDER · DISEÑAR · CONECTAR':'WEB · SOFTWARE · INTEGRACIÓN'}</span><span>{String(i+1).padStart(2,'0')} / 05</span></div>
 </AbsoluteFill>;
};
const Film=()=> <AbsoluteFill style={{fontFamily:'Nienfos, sans-serif',background:C.ink}}><style>{`@font-face{font-family:Nienfos;src:url('${A('NotoSans-Regular.ttf')}');font-weight:400}@font-face{font-family:Nienfos;src:url('${A('NotoSans-Bold.ttf')}');font-weight:700}*{box-sizing:border-box}`}</style>{scenesV13.map((s,i)=><Sequence key={s.kind} from={s.start} durationInFrames={s.frames+(i<4?17:0)}><Shot i={i}/></Sequence>)}</AbsoluteFill>;
export const PresentationV13Root=()=> <Composition id="NienfosPresentacionV13" component={Film} durationInFrames={624} fps={30} width={720} height={1280}/>;
