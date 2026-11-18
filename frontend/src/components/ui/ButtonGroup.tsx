// Adapted from the Untitled UI Vite starter's ButtonGroup (MIT).
// See Untitled-UI-LICENSE.txt for attribution.
import {createContext, useContext, type ComponentPropsWithoutRef} from 'react';
import './buttonGroup.css';

type ButtonSize = 'sm' | 'md';
const ButtonGroupContext = createContext<ButtonSize>('md');

type GroupProps = ComponentPropsWithoutRef<'div'> & {size?: ButtonSize};
export function ButtonGroup({children, size = 'md', className, ...props}: GroupProps) {
 return (
  <ButtonGroupContext.Provider value={size}>
   <div role="group" {...props} className={['barq-button-group', className].filter(Boolean).join(' ')}>
    {children}
   </div>
  </ButtonGroupContext.Provider>
 );
}

export function ButtonGroupItem({className, ...props}: ComponentPropsWithoutRef<'button'>) {
 const size = useContext(ButtonGroupContext);
 return <button type="button" {...props} data-size={size}
  className={['barq-button-group-item', className].filter(Boolean).join(' ')}/>;
}
