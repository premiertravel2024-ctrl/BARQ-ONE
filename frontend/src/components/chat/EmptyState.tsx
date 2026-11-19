import {motion,useReducedMotion} from 'framer-motion';
import {ArrowUpRight,Code2,MessageCircle,Monitor,Orbit} from 'lucide-react';
import {useApp} from '../../store';

export function EmptyState({onSuggestion,onHologram}:{onSuggestion:(text:string)=>void;onHologram:()=>void}){
 const ar=useApp(state=>state.language)==='ar',reduced=useReducedMotion();
 const suggestions=ar?[
  {icon:MessageCircle,title:'اتكلم مع برق',prompt:'ساعدني أرتّب يومي النهارده'},
  {icon:Monitor,title:'نفّذ أمر على الجهاز',prompt:'اعمل فولدر باسم تقارير على سطح المكتب'},
  {icon:Code2,title:'ابدأ مهمة برمجة',prompt:'ابنيلي برنامج مصاريف شخصي لويندوز وطلّعلي EXE'},
 ]:[
  {icon:MessageCircle,title:'Talk to BARQ',prompt:'Help me plan my day'},
  {icon:Monitor,title:'Run a desktop command',prompt:'Create a folder named Reports on Desktop'},
  {icon:Code2,title:'Start a coding task',prompt:'Build a Windows expense tracker and give me an EXE'},
 ];
 return <div className="barq-empty-state barq-welcome">
  <div className="barq-welcome-inner">
   <section className="barq-welcome-hero">
    <div className="barq-welcome-copy">
     <h1>{ar?'عايز برق يعمل إيه؟':'What can BARQ do for you?'}</h1>
     <button className="barq-hero-action focus-ring" type="button" onClick={onHologram}>
      <Orbit size={19}/>{ar?'افتح الهولوجرام':'Open hologram'}<ArrowUpRight size={16} className="barq-direction-icon"/>
     </button>
    </div>
   </section>
   <div className="barq-quick-actions" aria-label={ar?'اقتراحات للبدء':'Quick starts'}>
    {suggestions.map((item,index)=><motion.button key={item.title} type="button" onClick={()=>onSuggestion(item.prompt)}
     initial={reduced?false:{opacity:0,y:8}} animate={{opacity:1,y:0}} transition={{delay:reduced?0:index*.05}}
     className="barq-suggestion-card focus-ring">
     <span className="barq-suggestion-icon"><item.icon size={19}/></span>
     <span className="barq-suggestion-title">{item.title}</span>
     <ArrowUpRight size={15} className="barq-suggestion-arrow barq-direction-icon"/>
     <span className="barq-suggestion-prompt">{item.prompt}</span>
    </motion.button>)}
   </div>
  </div>
 </div>;
}
