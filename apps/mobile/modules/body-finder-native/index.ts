import { requireNativeModule } from 'expo-modules-core';
export type NativeApi={getCapabilitiesJson():string;getWifiRssi():number|null;updateLocalState(baseline:number|null,sigma:number|null,scanning:boolean):boolean;startFabric(nodeId:string|null,displayName:string|null,sessionId:string|null):Promise<boolean>;stopFabric():boolean;getPeersJson():string;getLocalAdvertisementJson():string};
export default requireNativeModule<NativeApi>('BodyFinderNative');
