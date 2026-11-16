import type { Transition } from 'framer-motion';
export const motionTokens = {
  duration:{micro:.18,ripple:.5,shine:.7,tooltip:.16,success:.4,toast:4.5,stagger:.03,enter:.24,modal:.22},
  spring:{press:{type:'spring',stiffness:500,damping:30},soft:{type:'spring',stiffness:320,damping:30},sidebar:{type:'spring',stiffness:280,damping:32},toggle:{type:'spring',stiffness:520,damping:32}},
  distance:{lift:-1.5,message:8,menu:7,tooltip:4,magnetic:6},
  ease:[.2,.8,.2,1] as [number,number,number,number]
} as const;
export const fades = {hidden:{opacity:0,y:motionTokens.distance.message},show:{opacity:1,y:0}};
export function fadeTransition(reduced:boolean):Transition {return {duration:reduced?0.08:motionTokens.duration.enter,ease:motionTokens.ease};}
