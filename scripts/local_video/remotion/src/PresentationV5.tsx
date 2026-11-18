import React from 'react';
import {AbsoluteFill,Composition,Img,Sequence,interpolate,staticFile,useCurrentFrame} from 'remotion';
const A=(s:string)=>staticFile('campaign/'+s);
const ink='#142a32',paper='#f4f6f5',blue='#a7c7ce';
const clamp={extrapolateLeft:'clamp',extrapolateRight:'clamp'} as const;
const e=(f:number,d=0,n=24)=>1-Math.pow(1-interpolate(f,[d,d+n],[0,1],clamp),4);
export const presentationV5Scenes=[
 {title:['Esto es','Nienfos.'],label:'Webs y software para tu negocio',kind:'intro',light:false,frames:113},
 {title:['Entender primero.','Decidir mejor.'],label:'Escuchamos lo que necesitás.',kind:'listen',light:true,frames:135},
 {title:['Verlo. Probarlo.','Mejorarlo.'],label:'Revisás los avances con nosotros.',kind:'design',light:false,frames:141},
 {title:['Conectar para','simplificar.'],label:'Integramos las herramientas que ya usás.',kind:'build',light:true,frames:145},
 {title:['Ideas que ya','son proyectos.'],label:'Chrem Propiedades · Consultora RD',kind:'clients',light:false,frames:105},
 {title:['Contanos qué','tenés en mente.'],label:'Diseño. Desarrollo. Acompañamiento.',kind:'close',light:true,frames:90},
];
// Low-contrast aligned grid; gentle cell emphasis keeps the approved spatial identity.
const Field:React.FC<{time:number;light:boolean}>=({time,light})=><AbsoluteFill style={{overflow:'hidden',background:light?paper:ink}}>
 <AbsoluteFill style={{background:light?'radial-gradient(ellipse at 90% 70%,#e4ece8,transparent 70%)':'radial-gradient(ellipse at 90% 70%,#25434e,transparent 75%)'}}/>
 <svg width="720" height="1280" style={{position:'absolute'}}>
 {[0,1,2,3,4,5,6].map(i=><path key={'v'+i} d={`M${48+i*104} 0V1280`} stroke={light?ink:blue} strokeOpacity={light?.055:.075} strokeWidth=".65"/>)}
 {Array.from({length:13},(_,i)=><path key={'h'+i} d={`M0 ${16+i*104}H720`} stroke={light?ink:blue} strokeOpacity={light?.055:.075} strokeWidth=".65"/>)}
 {[{x:464,y:536},{x:152,y:848},{x:360,y:224},{x:48,y:1056}].map((c,i)=><rect key={i} x={c.x} y={c.y} width="104" height="104" fill={light?ink:blue} opacity={.012+(1+Math.sin(time/60+i*1.8))*.012}/>)}
 </svg>
 </AbsoluteFill>;
const Window:React.FC<{file:string;width:number;height:number;label:string}>=({file,width,height,label})=><div style={{width,height,background:paper,border:'1px solid #ffffff66',borderRadius:9,overflow:'hidden',boxShadow:'0 20px 50px #051c2840'}}><div style={{height:26,background:'#e4ebe7',display:'flex',alignItems:'center',gap:5,paddingLeft:11}}>{[0,1,2].map(i=><span key={i} style={{width:4,height:4,borderRadius:5,background:'#8ba2aa'}}/>)}<span style={{fontSize:9,color:ink,marginLeft:13}}>{label}</span></div><Img src={A(file)} style={{width:'100%',height:height-26,objectFit:'cover',objectPosition:'left top'}}/></div>;
const flows={
 listen:{nodes:[['TU NECESIDAD','Nos contás qué necesitás'],['ESCUCHA Y ANÁLISIS','Entendemos tu negocio'],['POR ESO','Acordamos un alcance claro']],note:'Un punto de partida compartido.'},
 design:{nodes:[['PROPUESTA','Te mostramos el diseño'],['TU PARTICIPACIÓN','Lo probás y nos contás'],['CON TU DEVOLUCIÓN','Lo ajustamos juntos']],note:'Tu experiencia orienta los cambios.'},
 build:{nodes:[['PUNTO DE PARTIDA','Herramientas separadas'],['INTEGRACIÓN A MEDIDA','Conectamos la información'],['ASÍ SIMPLIFICAMOS','Menos tareas repetidas']],note:'Tus sistemas trabajan conectados.'},
};
const Workflow:React.FC<{kind:string;f:number;light:boolean}>=({kind,f,light})=>{
 const flow=flows[kind as keyof typeof flows],fg=light?ink:paper;
 return <div style={{position:'absolute',left:48,top:555,width:624,height:535}}>
 <svg width="624" height="480" style={{position:'absolute'}}>{[0,1].map(i=>{
 const q=e(f,28+i*32,24),y=112+i*158;
 return <g key={i}><path d={`M312 ${y}V${y+44}`} pathLength="1" stroke={light?'#7f9ea7':blue} strokeWidth="2" strokeDasharray="1" strokeDashoffset={1-q}/><path d={`M306 ${y+37}L312 ${y+44}L318 ${y+37}`} fill="none" stroke={light?'#7f9ea7':blue} strokeWidth="2" opacity={q}/><circle cx="312" cy={y+44*((f/35)%1)} r="3" fill={light?ink:blue} opacity={q*.8}/></g>;
 })}</svg>
 {flow.nodes.map(([label,text],i)=>{
 const q=e(f,8+i*32,22),result=i===2;
 return <div key={label} style={{position:'absolute',left:25,top:i*158,width:574,height:112,padding:'17px 23px',border:`1px solid ${result?(light?ink:blue):'#7f9ea760'}`,borderRadius:10,background:result?(light?ink:blue):(light?'#f4f6f5f5':'#19343df5'),color:result?(light?paper:ink):fg,opacity:q,transform:`translateY(${(1-q)*27}px)`}}>
 <div style={{fontSize:12,letterSpacing:1.7,opacity:.72,marginBottom:10}}>{label}</div><div style={{display:'flex',alignItems:'center',gap:18,fontSize:26,letterSpacing:-.6,fontWeight:result?700:400}}><span style={{fontSize:15,opacity:.6,minWidth:20}}>0{i+1}</span>{text}<span style={{marginLeft:'auto',fontSize:23,opacity:result?e(f,89):.6}}>{result?'✓':kind==='design'?'↗':'↓'}</span></div>
 </div>;
 })}
 <div style={{position:'absolute',top:480,left:25,right:25,textAlign:'center',fontSize:20,opacity:e(f,90),color:light?'#506e77':blue}}>{flow.note}</div>
 </div>;
};
const Shot:React.FC<{index:number;start:number}>=({index,start})=>{
 const f=useCurrentFrame(),s=presentationV5Scenes[index],fg=s.light?ink:paper;
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
const PresentationV5=()=>{let t=0;return <AbsoluteFill style={{background:ink}}><style>{`@font-face{font-family:Nienfos;src:url('${A('NotoSans-Regular.ttf')}');font-weight:400}@font-face{font-family:Nienfos;src:url('${A('NotoSans-Bold.ttf')}');font-weight:700}*{box-sizing:border-box}`}</style>{presentationV5Scenes.map((s,i)=>{const start=t;t+=s.frames;return <Sequence key={i} from={start} durationInFrames={s.frames+(i<5?17:0)}><Shot index={i} start={start}/></Sequence>})}</AbsoluteFill>};
export const PresentationV5Root=()=> <Composition id="NienfosPresentacionV5" component={PresentationV5} durationInFrames={729} fps={30} width={720} height={1280}/>;
