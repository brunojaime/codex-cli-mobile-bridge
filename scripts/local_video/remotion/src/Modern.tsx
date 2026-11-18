import React from 'react';
import {AbsoluteFill, Img, Sequence, interpolate, staticFile, useCurrentFrame} from 'remotion';

const black = '#142b34';
const cream = '#f4f3ed';
const lime = '#d7f56b';
const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;
const reveal = (f: number, delay = 0) => {
  const t = interpolate(f, [delay, delay + 16], [0, 1], clamp);
  return 1 - Math.pow(1 - t, 4);
};
const Line: React.FC<{children: React.ReactNode; delay?: number; color?: string; size?: number}> = ({children, delay = 0, color, size = 100}) => {
  const f = useCurrentFrame();
  return <div style={{overflow: 'hidden', paddingBottom: 12, marginBottom: -12}}>
    <div style={{fontSize: size, fontWeight: 750, letterSpacing: -6, lineHeight: 1.06, color,
      transform: `translateY(${(1-reveal(f, delay))*(delay===0?14:110)}%)`}}>{children}</div>
  </div>;
};

const Orbit: React.FC<{light?: boolean}> = ({light = false}) => {
  const f = useCurrentFrame();
  return <div style={{position:'absolute',left:100,top:700,width:520,height:400,transform:`rotate(${f*.45-20}deg) scale(${.85+reveal(f)*.15})`}}>
    {[0,1,2].map(i=><div key={i} style={{position:'absolute',width:500,height:230,left:10,top:85,
      border:`2px solid ${light ? black : lime}`,borderRadius:'50%',transform:`rotate(${i*60}deg)`,opacity:i===0 ? 1:.5}}/>)}
    <div style={{position:'absolute',left:231,top:175,width:52,height:52,borderRadius:16,background:light ? black : lime,transform:`rotate(${45+f}deg)`}}/>
  </div>;
};

const Panel: React.FC<{index: number; duration: number}> = ({index,duration}) => {
  const f = useCurrentFrame();
  const light = index===1 || index===4;
  const exit = interpolate(f,[duration-9,duration],[0,1],clamp);
  const bg = index===2 ? lime : light ? cream : black;
  const fg = light || index===2 ? black : cream;
  return <AbsoluteFill style={{background:bg,color:fg,fontFamily:'Arial, sans-serif',overflow:'hidden'}}>
    <AbsoluteFill style={{transform:`translateY(${-exit*28}px)`,opacity:1-exit*.4}}>
      <div style={{position:'absolute',top:90,left:54,right:54,display:'flex',justifyContent:'space-between',fontSize:17,letterSpacing:3,fontWeight:600}}>
        <span>NIENFOS</span><span>IDEAS → ACCIÓN</span>
      </div>
      <div style={{position:'absolute',top:280,left:54,right:42}}>
        {index===0 && <><Line>Ideas que</Line><Line color={lime} delay={4}>mueven.</Line><div style={{marginTop:36,fontSize:25,opacity:reveal(f,12)}}>De imaginar a hacer.</div></>}
        {index===1 && <><Line>Menos</Line><Line delay={4}>fricción.</Line><div style={{marginTop:36,fontSize:25,opacity:reveal(f,12)}}>Lo complejo, más simple.</div></>}
        {index===2 && <><Line size={112}>Más</Line><Line size={76} delay={4}>posibilidades.</Line><div style={{marginTop:36,fontSize:25,opacity:reveal(f,12)}}>Espacio para lo que viene.</div></>}
        {index===3 && <>{['Pensar.','Diseñar.','Construir.'].map((s,i)=><div key={s} style={{marginBottom:18}}><Line size={88} delay={i*7} color={i===2?lime:cream}>{s}</Line></div>)}<div style={{marginTop:44,width:600,height:5,background:lime,transform:`scaleX(${reveal(f,14)})`,transformOrigin:'left'}}/></>}
        {index===4 && <><Line>Hagamos</Line><Line delay={4}>que pase.</Line><div style={{marginTop:40,fontSize:28,opacity:reveal(f,12)}}>Tu próxima idea empieza acá. ↗</div></>}
      </div>
      {(index===0 || index===2) && <Orbit light={index===2}/>}
      {index===1 && <div style={{position:'absolute',top:780,left:54,right:54,display:'flex',gap:18,alignItems:'end',height:220}}>{[.45,.8,.55,1,.65].map((h,i)=><div key={i} style={{flex:1,height:`${h*100}%`,background:i===3?black:'#c6d4d0',borderRadius:14,transform:`scaleY(${reveal(f,i*3)})`,transformOrigin:'bottom'}}/>)}</div>}
      {index===3 && <div style={{position:'absolute',left:54,bottom:230,fontSize:150,letterSpacing:-10,color:'#54737c',transform:`translateX(${(1-reveal(f,12))*80}px)`}}>→</div>}
      {index===4 && <div style={{position:'absolute',left:54,right:54,bottom:200,borderTop:'1px solid #cad3cf',paddingTop:42,opacity:reveal(f,14)}}><Img src={staticFile('nienfos.png')} style={{width:490,height:170,objectFit:'contain',objectPosition:'left'}}/></div>}
      <div style={{position:'absolute',bottom:88,left:54,right:54,display:'flex',justifyContent:'space-between',fontSize:16,letterSpacing:2,opacity:.7}}><span>DE LA IDEA A LO POSIBLE</span><span>0{index+1} / 05</span></div>
    </AbsoluteFill>
  </AbsoluteFill>;
};

const durations=[90,75,90,60,105];
export const Modern: React.FC = () => {
  const f=useCurrentFrame();
  let start=0;
  return <AbsoluteFill style={{background:black}}>
    {durations.map((duration,index)=>{
      const from=start;start+=duration;
      return <Sequence key={index} from={from} durationInFrames={duration}><Panel index={index} duration={duration}/></Sequence>;
    })}
    <div style={{position:'absolute',top:0,left:0,height:5,background:lime,width:`${(f+1)/420*100}%`}}/>
  </AbsoluteFill>;
};
