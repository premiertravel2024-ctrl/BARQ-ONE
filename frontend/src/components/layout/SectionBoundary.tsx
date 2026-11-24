import {Component,type ReactNode} from 'react';

type Props={ar:boolean;children:ReactNode};

export class SectionBoundary extends Component<Props,{failed:boolean}>{
 state={failed:false};

 static getDerivedStateFromError(){
  return {failed:true};
 }

 render(){
  if(!this.state.failed)return this.props.children;
  const {ar}=this.props;
  return <section role="alert" className="m-4 space-y-3 rounded-lg border border-stroke bg-surface p-5">
   <p className="text-sm font-semibold">{ar?'حصل خطأ أثناء فتح القسم.':'This section could not open.'}</p>
   <button type="button" className="focus-ring rounded-sm border border-stroke px-4 py-2 text-sm"
    onClick={()=>this.setState({failed:false})}>{ar?'حاول مرة تانية':'Try again'}</button>
  </section>;
 }
}
