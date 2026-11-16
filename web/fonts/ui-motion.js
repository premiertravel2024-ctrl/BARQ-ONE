/* Shared interaction timing: the UI reads CSS custom properties from this one configuration. */
window.RouterMotion = Object.freeze({
  hoverMs: 180,
  fastMs: 160,
  menuStaggerMs: 30,
  suggestionStaggerMs: 60,
  modalMs: 210,
  messageMs: 240,
  sidebarMs: 260,
  successMs: 1500,
  shakeMs:300,
  pulseMs:1300,
  spinMs:750,
  ease: 'cubic-bezier(.2,.8,.2,1)',
  spring: 'cubic-bezier(.2,1.25,.3,1)',
  movement: 8,
  pressScale: .96
});
(() => {
  const m=window.RouterMotion, st=document.documentElement.style;
  Object.entries({
    '--motion-hover':m.hoverMs+'ms','--motion-fast':m.fastMs+'ms',
    '--motion-modal':m.modalMs+'ms','--motion-message':m.messageMs+'ms',
    '--motion-sidebar':m.sidebarMs+'ms','--motion-success':m.successMs+'ms',
    '--motion-shake':m.shakeMs+'ms','--motion-pulse':m.pulseMs+'ms','--motion-spin':m.spinMs+'ms',
    '--motion-ease':m.ease,'--motion-spring':m.spring,
    '--motion-rise':m.movement+'px','--motion-press':m.pressScale
  }).forEach(([key,val])=>st.setProperty(key,String(val)));
})();
