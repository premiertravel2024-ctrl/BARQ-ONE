// Convert the ACTUAL device sample rate to 16 kHz mono PCM16.
// Windows microphones commonly run at 44.1/48 kHz even if an AudioContext
// requests 16 kHz. Sending unconverted frames labelled as 16 kHz distorts
// speech and changes timing for silence detection.
// 20-ms packets keep latency bounded and reduce lost syllables on shutdown.
class BarqCapture extends AudioWorkletProcessor {
 constructor(){
  super();
  this.packet=new Int16Array(320);this.used=0;
  this.inputPosition=0;this.nextOutputPosition=0;this.previousSample=0;
  this.step=sampleRate/16000;
 }
 emit(value){
  const clipped=Math.max(-1,Math.min(1,value));
  this.packet[this.used++]=Math.round(clipped*(clipped<0?32768:32767));
  if(this.used===this.packet.length){
   this.port.postMessage(this.packet.buffer,[this.packet.buffer]);
   this.packet=new Int16Array(320);this.used=0;
  }
 }
 process(inputs){
  const channels=inputs[0];if(!channels||!channels.length)return true;
  const first=channels[0],second=channels.length>1?channels[1]:null;
  for(let i=0;i<first.length;i++){
   const sample=second?(first[i]+second[i])*.5:first[i];
   const position=this.inputPosition+i;
   while(this.nextOutputPosition<=position){
    const fraction=Math.max(0,Math.min(1,this.nextOutputPosition-(position-1)));
    this.emit(this.previousSample+(sample-this.previousSample)*fraction);
    this.nextOutputPosition+=this.step;
   }
   this.previousSample=sample;
  }
  this.inputPosition+=first.length;
  return true;
 }
}
registerProcessor('barq-capture',BarqCapture);
