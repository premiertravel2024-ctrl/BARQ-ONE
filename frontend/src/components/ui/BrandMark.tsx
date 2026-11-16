import type {CSSProperties} from 'react';
/** Source: BARQ_App_Icon(1).ico. Symbol pixels are preserved; only their ink color differs by theme. */
export function BrandMark({size=40,className='',style}:{size?:number;className?:string;style?:CSSProperties}){
 return <span className={`barq-mark ${className}`} style={{width:size,height:size,...style}} aria-hidden="true">
  <img className="barq-mark-on-dark" src="/brand/barq-mark-dark.png" alt="" width={size} height={size} draggable={false}/>
  <img className="barq-mark-on-light" src="/brand/barq-mark-light.png" alt="" width={size} height={size} draggable={false}/>
 </span>
}
export function BrandLockup({compact=false}:{compact?:boolean}){
 return <span className="barq-lockup" dir="ltr"><BrandMark size={compact?32:40}/>{!compact&&<span className="barq-wordmark">BARQ</span>}</span>
}
