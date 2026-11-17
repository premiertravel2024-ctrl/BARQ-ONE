export type OnePage =
 | 'center' | 'chat' | 'voice' | 'mission' | 'library' | 'installed' | 'tools'
 | 'monitor' | 'resources' | 'wallpapers' | 'watch' | 'music' | 'stories'
 | 'automation' | 'settings';

export type AppSection=OnePage|'playground';
export type AppAction={section:AppSection;mode?:string|null};
