export type UiAudit={
 workspace:string;checked_files:number;total_ui_files:number;truncated:boolean;
 findings:Array<{file:string;line:number;kind:string;message:string;severity:string}>;
 observations:Record<string,{count:number;examples:string[]}>;
 next_checks:string[];visual_verified:false;runtime_verified:false;scope:string;
};
