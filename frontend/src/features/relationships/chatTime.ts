export const OPERATOR_TIME_ZONE="America/Chicago" as const;

export function formatChatTime(value:string|Date,locale="en-US"){return new Intl.DateTimeFormat(locale,{hour:"numeric",minute:"2-digit",timeZone:OPERATOR_TIME_ZONE}).format(new Date(value));}
export function formatChatCalendarDate(value:string|Date,locale="en-US"){return new Intl.DateTimeFormat(locale,{dateStyle:"medium",timeZone:OPERATOR_TIME_ZONE}).format(new Date(value));}
export function formatChatDay(value:string|Date,now:Date=new Date()){const formatter=new Intl.DateTimeFormat("en-US",{timeZone:OPERATOR_TIME_ZONE,year:"numeric",month:"long",day:"numeric"});const key=formatter.format(new Date(value)),today=formatter.format(now),yesterday=formatter.format(new Date(now.getTime()-86400000));return key===today?"TODAY":key===yesterday?"YESTERDAY":key.toUpperCase();}
