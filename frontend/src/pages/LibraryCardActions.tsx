import type {ReactNode} from 'react';
import {ArrowLeft} from 'lucide-react';

export type LibraryCardSecondaryAction={
 id:string;
 label:string;
 icon:ReactNode;
 onClick:()=>void;
 pressed?:boolean;
};

export function LibraryCardActions({label,onPrimary,ariaLabel,secondary=[]}:{
 label:string;
 onPrimary:()=>void;
 ariaLabel?:string;
 secondary?:LibraryCardSecondaryAction[];
}){
 return <div className="bs-card-actions">
  <button className="bs-card-primary" type="button" onClick={onPrimary}
   aria-label={ariaLabel||label}>
   <span>{label}</span><ArrowLeft size={15} aria-hidden="true"/>
  </button>
  {secondary.map(action=><button
   key={action.id} className="bs-card-secondary" type="button"
   title={action.label} aria-label={action.label}
   aria-pressed={action.pressed} onClick={action.onClick}>
   {action.icon}
  </button>)}
 </div>;
}
