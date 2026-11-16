import type {ButtonProps} from './Button';
import {Button} from './Button';
import {Tooltip} from './Tooltip';
type Props=Omit<ButtonProps,'variant'|'children'> & {label:string;variant?:ButtonProps['variant'];tooltipSide?:'top'|'bottom'};
export function IconButton({label,tooltipSide,variant='icon',...props}:Props){return <Tooltip label={label} side={tooltipSide}><Button {...props} aria-label={label} variant={variant}/></Tooltip>}
