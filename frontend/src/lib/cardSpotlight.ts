import type {PointerEvent} from 'react';

export function moveCardSpotlight(event:PointerEvent<HTMLDivElement>){
 if(event.pointerType!=='mouse'||!(event.target instanceof Element))return;
 const card=event.target.closest<HTMLElement>('[data-spotlight]');
 if(!card||window.matchMedia('(prefers-reduced-motion: reduce)').matches)return;
 const {left,top}=card.getBoundingClientRect();
 card.style.setProperty('--spotlight-x',`${event.clientX-left}px`);
 card.style.setProperty('--spotlight-y',`${event.clientY-top}px`);
}
