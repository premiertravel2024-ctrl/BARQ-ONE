import {useEffect,useState,type FormEvent} from 'react';
import {Cloud} from 'lucide-react';
const KEY='barq-online-library-url';

function validated(value:string):string {
 try {
  const url=new URL(value.trim());
  if(url.protocol!=='https:'||url.username||url.password||url.search||url.hash)return '';
  return url.origin+url.pathname.replace(/\/+$/,'');
 }catch{return '';}
}
export function onlineLibraryUrl():string {
 let saved='';
 try{saved=localStorage.getItem(KEY)||'';}catch{/* private browsing */}
 return validated(saved||import.meta.env.VITE_BARQ_LIBRARY_URL||'');
}
export function OnlineLibraryLink({ar}:{ar:boolean}){
 const [url,setUrl]=useState(onlineLibraryUrl);
 useEffect(()=>{
  const changed=()=>setUrl(onlineLibraryUrl());
  window.addEventListener('barq:online-library',changed);
  return()=>window.removeEventListener('barq:online-library',changed);
 },[]);
 if(!url)return null;
 return <a className="bs-muted-btn" href={url} target="_blank" rel="noopener noreferrer"
  aria-label={ar?'افتح المكتبة المشتركة على الإنترنت':'Open shared online library'}>
  <Cloud size={16}/>{ar?'المكتبة أونلاين':'Online library'}
 </a>;
}
export function OnlineLibrarySettings({ar}:{ar:boolean}){
 const [value,setValue]=useState(onlineLibraryUrl);
 const [error,setError]=useState('');
 function submit(event:FormEvent){
  event.preventDefault();
  const url=validated(value);
  if(!url){setError(ar?'لازم رابط HTTPS صحيح للمكتبة.':'Enter a valid HTTPS library URL.');return;}
  try{
   localStorage.setItem(KEY,url);
   window.dispatchEvent(new Event('barq:online-library'));
   setError('');
  }catch{setError(ar?'تعذّر حفظ الرابط محليًا.':'Could not save the library link.');}
 }
 return <form className="bs-local-series-form" onSubmit={submit}>
  <label>{ar?'رابط المكتبة المشتركة':'Shared library URL'}
   <input type="url" dir="ltr" value={value} onChange={event=>setValue(event.target.value)}
    placeholder="https://barq-one-library.example.workers.dev" required/></label>
  <button className="bs-muted-btn" type="submit">{ar?'حفظ الرابط':'Save link'}</button>
  <OnlineLibraryLink ar={ar}/>
  {error&&<p className="bs-alert" role="alert">{error}</p>}
 </form>;
}
