import {useEffect,useRef} from 'react';
import {speechPlaybackLevel} from '../../lib/speechGlow';

type Point=[number,number,number];
type Orbit={radius:number;tilt:number;axis:number;speed:number;segments:Array<[number,number]>};

const TAU=Math.PI*2;
const orbits:Orbit[]=[
 {radius:118,tilt:.23,axis:-.48,speed:.20,segments:[[.04,.34],[.40,.70],[.79,.99]]},
 {radius:106,tilt:1.02,axis:.63,speed:-.23,segments:[[.02,.23],[.29,.52],[.56,.83],[.92,.98]]},
 {radius:94,tilt:.87,axis:-.81,speed:.33,segments:[[.03,.32],[.40,.59],[.63,.97]]},
];
const sphere:Point[]=Array.from({length:404},(_,index)=>{
 const y=1-2*(index+.5)/404;
 const ring=Math.sqrt(1-y*y);
 const angle=index*Math.PI*(3-Math.sqrt(5));
 return [ring*Math.cos(angle)*72,y*72,ring*Math.sin(angle)*72];
});

export function HologramCore({phase,level}:{phase:string;level:number}){
 const canvas=useRef<HTMLCanvasElement>(null);
 const state=useRef({phase,level});
 const redrawStatic=useRef<()=>void>();
 useEffect(()=>{state.current={phase,level};redrawStatic.current?.();},[phase,level]);
 useEffect(()=>{
  const surface=canvas.current;
  const ctx=surface?.getContext('2d');
  if(!surface||!ctx)return;
  const motion=window.matchMedia('(prefers-reduced-motion: reduce)');
  let frame=0,width=0,height=0,scale=1,lastPaint=-Infinity;
  const draw=(time:number)=>{
   if(!width||!height)return;
   const color=state.current.phase==='approval'?'255,183,102':
    state.current.phase==='speaking'?'125,233,255':'80,205,255';
   const active=['processing','executing','busy'].includes(state.current.phase);
   const voice=state.current.phase==='speaking'?speechPlaybackLevel()??0:
    state.current.phase==='hearing'?state.current.level:0;
   const response=motion.matches?0:Math.max(0,Math.min(voice,1));
   const unit=Math.min(width/500,height/342);
   ctx.setTransform(scale,0,0,scale,0,0);
   ctx.clearRect(0,0,width,height);
   ctx.translate(width/2,height*.44);
   ctx.scale(unit,unit);
   const t=time/1000;
   const ink=(alpha:number)=>`rgba(${color},${alpha})`;
   const project=([x,y,z]:Point)=>{
    const depth=440/(440-z);
    return [x*depth,y*depth,z] as const;
   };
   const glow=ctx.createRadialGradient(0,0,0,0,0,156);
   glow.addColorStop(0,ink(.28+response*.11));
   glow.addColorStop(.42,ink(.11));
   glow.addColorStop(1,ink(0));
   ctx.fillStyle=glow;
   ctx.fillRect(-156,-156,312,312);

   const ellipse=(x:number,y:number,rx:number,ry:number)=>{
    ctx.beginPath();ctx.ellipse(x,y,rx,ry,0,0,TAU);ctx.stroke();
   };
   ctx.lineWidth=1;
   ctx.strokeStyle=ink(.16);ellipse(0,0,130,130);
   ctx.strokeStyle=ink(.07);ellipse(0,0,148,148);
   ctx.strokeStyle=ink(.22);ellipse(0,134,142,23);
   ctx.strokeStyle=ink(.13);ellipse(0,134,117,15);
   ctx.strokeStyle=ink(.37);ellipse(0,134,83,9);

   for(let index=0;index<72;index++){
    const angle=index/72*TAU;
    const edge=index%6===0?140:136;
    ctx.strokeStyle=ink(index%6===0?.42:.17);
    ctx.beginPath();ctx.moveTo(Math.cos(angle)*131,Math.sin(angle)*131);
    ctx.lineTo(Math.cos(angle)*edge,Math.sin(angle)*edge);ctx.stroke();
   }

   for(const orbit of orbits){
    const rotation=t*orbit.speed*(active?2.4:1);
    const axis=orbit.axis+Math.sin(rotation*.35)*.22;
    const plane=(angle:number)=>{
     const x=Math.cos(angle)*orbit.radius;
     const y=Math.sin(angle)*orbit.radius;
     return project([x*Math.cos(axis)-y*Math.cos(orbit.tilt)*Math.sin(axis),
      x*Math.sin(axis)+y*Math.cos(orbit.tilt)*Math.cos(axis),y*Math.sin(orbit.tilt)]);
    };
    for(const [start,end] of orbit.segments){
     for(let step=0;step<28;step++){
      const a=plane((start+(end-start)*step/28)*TAU+rotation);
      const b=plane((start+(end-start)*(step+1)/28)*TAU+rotation);
      ctx.strokeStyle=ink(.33+.30*(a[2]/orbit.radius));
      ctx.lineWidth=a[2]>12?2:1;
      ctx.beginPath();ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1]);ctx.stroke();
     }
    }
    const [x,y,z]=plane(rotation);
    ctx.fillStyle=ink(z>0?1:.42);
    ctx.beginPath();ctx.arc(x,y,2.7,0,TAU);ctx.fill();
   }

   const offset=t*(active?.55:.23);
   const expansion=1+response*.21;
   for(const [x,y,z] of sphere){
    const depth=z*Math.cos(offset)-x*Math.sin(offset);
    const sx=x*Math.cos(offset)+z*Math.sin(offset);
    const [px,py]=project([sx*expansion,(y+depth*.13)*expansion,depth]);
    ctx.fillStyle=ink(.24+((depth+72)/144)*.66);
    const size=depth>0?2.2:1.25;
    ctx.fillRect(px,py,size,size);
   }

   const beam=ctx.createLinearGradient(0,55,0,137);
   beam.addColorStop(0,ink(0));beam.addColorStop(1,ink(.15+response*.20));
   ctx.fillStyle=beam;
   ctx.beginPath();ctx.moveTo(-44,58);ctx.lineTo(44,58);ctx.lineTo(78,134);ctx.lineTo(-78,134);
   ctx.closePath();ctx.fill();

   for(const side of [-1,1]){
    for(let i=0;i<17;i++){
     const x=side*(151+i*3.7);
     const wave=.5+.5*Math.sin(i*.79+t*4);
     const length=3+wave*(6+response*32+(active?8:0))*Math.sin((i+1)/18*Math.PI);
     ctx.strokeStyle=ink(.18+wave*.37);
     ctx.lineWidth=1.5;ctx.beginPath();
     ctx.moveTo(x,45-length/2);ctx.lineTo(x,45+length/2);ctx.stroke();
    }
   }
  };
  function animate(time:number){
   if(time-lastPaint>=1000/30){
    draw(time);
    lastPaint=time;
   }
   frame=requestAnimationFrame(animate);
  }
  function resize(){
   const bounds=surface!.getBoundingClientRect();
   width=bounds.width;height=bounds.height;scale=Math.min(window.devicePixelRatio||1,2);
   surface!.width=Math.max(1,Math.round(width*scale));
   surface!.height=Math.max(1,Math.round(height*scale));
   draw(0);
  }
  const observer=typeof ResizeObserver==='undefined'?null:new ResizeObserver(resize);
  const updateMotion=()=>{
   cancelAnimationFrame(frame);
   if(motion.matches)draw(0);
   else frame=requestAnimationFrame(animate);
  };
  redrawStatic.current=()=>{if(motion.matches)draw(0);};
  observer?.observe(surface);
  if(!observer)window.addEventListener('resize',resize);
  motion.addEventListener('change',updateMotion);
  resize();updateMotion();
  return()=>{redrawStatic.current=undefined;cancelAnimationFrame(frame);observer?.disconnect();window.removeEventListener('resize',resize);motion.removeEventListener('change',updateMotion);};
 },[]);
 return <canvas ref={canvas} className="barq-hologram-art" data-phase={phase} aria-hidden="true"/>;
}
