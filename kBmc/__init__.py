# Kage Park
# Inteligent BMC Tool
# Version 2

import re
import os
import sys
import time
import json
import threading
from kmport import *

#printf_ignore_empty=True

# cancel() : True : Cancel whole bmc process
# stop     : True : stop the running process
#### Return #####
# True     : Good
# False    : False
# <+N>     : Good level user define : if rc: ok
# 1        : Good level user define : if rc == True: ok
# 0        : False level user define (like as cancel) : if rc == False : this is False
# (True == 1, False == 0)
# <STR>    : user define value      : if rc: ok

class Ipmitool:
    def __init__(self,**opts):
        self.__name__='ipmitool'
        self.tool_path=None
        self.log=opts.get('log',None)
        self.power_mode=opts.get('power_mode',{'on':['chassis power on'],'off':['chassis power off'],'reset':['chassis power reset'],'off_on':['chassis power off','chassis power on'],'on_off':['chassis power on','chassis power off'],'cycle':['chassis power cycle'],'status':['chassis power status'],'shutdown':['chassis power soft']})
        self.ready=True
        self.return_code={'ok':[0],'fail':[1]}
        if find_executable('ipmitool') is False:
            os.system('which apt >/dev/null && sudo apt install -y ipmitool || sudo yum install -y ipmitool')
            if find_executable('ipmitool') is False:
                self.ready=False

    def cmd_str(self,cmd,**opts):
        if not self.ready:
            printf('Install ipmitool package(yum install ipmitool)',log=self.log,log_level=1,dsp='e')
            return False,'ipmitool file not found',None,self.return_code,None
        cmd_a=cmd.split()
        option=opts.get('option','lanplus')
        if IsIn('ipmi',cmd_a,idx=0) and IsIn('power',cmd_a,idx=1) and Get(cmd_a,2) in self.power_mode:
            cmd_a[0] = 'chassis'
        elif IsIn('ipmi',cmd_a,idx=0) and IsIn('reset',cmd_a,idx=1):
            cmd_a=['mc','reset','cold']
        elif IsIn('ipmi',cmd_a,idx=0) and IsIn('lan',cmd_a,idx=1):
            if len(cmd_a) == 3 and cmd_a[2] in ['mac','dhcp','gateway','netmask']:
                cmd_a=['lan','print']
        elif IsIn('ipmi',cmd_a,idx=0) and IsIn('sensor',cmd_a,idx=1):
            #cmd_a=['sdr','type','Temperature']
            cmd_a=['sensor']
        passwd=opts.get('passwd')
        sym='"' if isinstance(passwd,str) and "'" in passwd else "'"
        return True,{'base':'''ipmitool -I %s -H {ip} -U {user} -P %s{passwd}%s '''%(option,sym,sym),'cmd':'''%s'''%(' '.join(cmd_a))},None,self.return_code,None


class Smcipmitool:
    def __init__(self,**opts):
        self.__name__='smc'
        self.smc_file=opts.get('smc_file',None)
        self.ready=True
        if not self.smc_file or not os.path.isfile(self.smc_file):
            self.ready=False
        self.log=opts.get('log',None)
        self.power_mode=opts.get('power_mode',{'on':['ipmi power up'],'off':['ipmi power down'],'reset':['ipmi power reset'],'off_on':['ipmi power down','ipmi power up'],'on_off':['ipmi power up','ipmi power down'],'cycle':['ipmi power cycle'],'status':['ipmi power status'],'shutdown':['ipmi power softshutdown']})
        self.return_code={'ok':[0,144],'error':[180],'err_bmc_user':[146],'err_connection':[145]}

    def cmd_str(self,cmd,**opts):
        cmd_a=cmd.split()
        if not self.ready:
            if self.smc_file:
                lmmsg='- SMCIPMITool({}) not found'.format(self.smc_file)
                printf(lmmsg,log=self.log,log_level=1,dsp='e')
            else:
                lmmsg='- Not assigned SMCIPMITool'
            return False,lmmsg,None,self.return_code,None
        if IsIn('chassis',cmd_a,idx=0) and IsIn('power',cmd_a,idx=1):
            cmd_a[0] == 'ipmi'
        elif IsIn('mc',cmd_a,idx=0) and IsIn('reset',cmd_a,idx=1) and IsIn('cold',cmd_a,idx=2):
            cmd_a=['ipmi','reset']
        elif IsIn('lan',cmd_a,idx=0) and IsIn('print',cmd_a,idx=1):
            cmd_a=['ipmi','lan','mac']
        elif IsIn('sdr',cmd_a,idx=0) and IsIn('Temperature',cmd_a,idx=2):
            cmd_a=['ipmi','sensor']
        passwd=opts.get('passwd')
        sym='"' if isinstance(passwd,str) and "'" in passwd else "'"
        if os.path.basename(self.smc_file).split('.')[-1] == 'jar':
            return True,{'base':'''sudo java -jar %s {ip} {user} %s{passwd}%s '''%(self.smc_file,sym,sym),'cmd':'''%s'''%(' '.join(cmd_a))},None,self.return_code,None
        else:
            return True,{'base':'''%s {ip} {user} %s{passwd}%s '''%(self.smc_file,sym,sym),'cmd':'''%s'''%(' '.join(cmd_a))},None,self.return_code,None

class Redfish:
    def __init__(self,**opts):
        self.power_on_tag='¯'
        self.power_up_tag='∸'
        self.power_off_tag='_'
        self.power_down_tag='⨪'
        self.power_unknown_tag='·'
        self.__name__='redfish'
        self.log=opts.get('log',None)
        if isinstance(opts.get('path'),dict):
            self.path=opts['path']
        else:
            self.path={
                'virtualmedia':'/redfish/v1/Managers/1/VirtualMedia',
                'floppyimage':'/redfish/v1/Managers/1/VirtualMedia/Floppy1',
                'Marvell':'Systems/1/Storage/MRVL.HA-RAID/Volumes/Controller.0.Volume.0',
                'LSI3108':'Systems/1/Storage/HA-RAID',
                'EthernetCount':'Systems/1/EthernetInterfaces',
                'PsuCount':'Chassis/1/Power',
                'BootOption':'Systems/1/BootOptions',
            }
        self.user=opts.get('user','ADMIN')
        self.passwd=opts.get('passwd','ADMIN')
        self.host=opts.get('host')

    def Cmd(self,cmd,host=None):
        if not host: host=self.host
        if cmd.startswith('/redfish/v1'):
            return "https://{}{}".format(host,cmd)
        elif cmd.startswith('redfish/v1'):
            return "https://{}/{}".format(host,cmd)
        elif cmd.startswith('https:') and 'redfish' in cmd.split('/') and host is None:
            return "{}".format(cmd)
        elif cmd.startswith('/'):
            return "https://{}/redfish/v1{}".format(host,cmd)
        else:
            return "https://{}/redfish/v1/{}".format(host,cmd)

    def Get(self,cmd,host=None):
        if not host: host=self.host
        if not isinstance(cmd,str): return False
        data = WEB().Request(self.Cmd(cmd,host=host),auth=(self.user, self.passwd))
        if data[0]:
            if data[1].status_code == 200:
                try:
                    return True,json.loads(data[1].text)
                except:
                    return False,data[1].text
            try:
                data_dic=json.loads(data[1].text)
                if 'error' in data_dic:
                    err_dic=data_dic.get('error',{})
                    if '@Message.ExtendedInfo' in err_dic:
                        err_msg=err_dic.get('@Message.ExtendedInfo',{})[0].get('Message')
                    elif 'Message' in err_dic:
                        err_msg=err_dic.get('Message')
                    else:
                        err_msg=err_dic
                    return False, err_msg
            except:
                return False,data[1].text
        return False,'Request Error'

    def Post(self,cmd,host=None,json=None,data=None,files=None,mode='post'):
        if not host: host=self.host
        if not isinstance(cmd,str): return False
        data = WEB().Request(self.Cmd(cmd,host=host),auth=(self.user, self.passwd),mode=mode,json=json,data=data,files=files)
        if data[0]:
            if data[1].status_code == 200:
                return True
            else:
                try: # sometimes, success with 202 code or maybe others(??)
                    tmp=FormData(data[1].text)
                    if next(iter(tmp)) == 'Success':
                        return True
                except:
                    pass
        return False

    def Data(self,data):
        ndata={}
        if isinstance(data,dict):
            ndata['child']={}
            for xx in data:
                if xx == '@odata.id':
                    ndata['path']=data.get(xx)
                elif xx == 'Name':
                    ndata['name']=data.get(xx)
                elif xx == 'UUID':
                    ndata['uuid']=data.get(xx)
                elif xx == 'RedfishVersion':
                    ndata['version']=data.get(xx)
                elif xx == 'Description':
                    ndata['desc']=data.get(xx)
                elif xx == 'Members':
                    for ii in data.get('Members'):
                        ndata['child'][os.path.basename(ii.get('@odata.id'))]=ii.get('@odata.id')
                else:
                    if isinstance(data[xx],dict):
                        ndata[xx]=data[xx].get('@odata.id')
        return ndata


    def Power(self,cmd='status',pxe=False,pxe_keep=False,uefi=False,sensor_up=0,sensor_down=0,timeout=600,silent_status_log=True):
        def get_current_power_state():
            ok,aa=self.Get('Systems/1')
            if not ok:
                if not silent_status_log: printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1)
                return 'unknown'
            current_power=aa.get('PowerState') if isinstance(aa,dict) and aa.get('PowerState') else 'unknown'
            if current_power == 'unknown':
                ok,aa=self.Get('Managers/1/Oem/Supermicro/SmartPower')
                if ok:
                    if isinstance(aa,dict):
                        current_power=aa.get('PowerStatus')
            if isinstance(current_power,str):
                return current_power
            return 'unknown'
        current_power=get_current_power_state().lower()
        if cmd == 'status':
            return current_power
        if cmd in ['on','off','shutdown','reboot','reset','off_on']:
            def cmd_state(cmd,on_s=['on'],off_s=['off','shutdown']):
                if cmd in on_s:
                    return 'on'
                elif cmd in off_s:
                    return 'off'
                return None
            if cmd_state(cmd) == current_power: return True
            #Set PXE Boot
            if pxe and cmd in ['on','reset','reboot','off_on']:
                pxe_str='ipxe' if uefi is True else 'pxe'
                if pxe_keep:
                    self.Boot(boot=pxe_str,keep='keep')
                else:
                    self.Boot(boot=pxe_str)
            #Do Power command
            if cmd == 'off_on':
                #Not off then turn off
                if current_power != 'off':
                    aa=self.Post('/Systems/1/Actions/ComputerSystem.Reset',json={'Action': 'Reset', 'ResetType': 'ForceOff'})
                    for i in range(0,600):
                        current_power=get_current_power_state().lower()
                        if current_power == 'off':
                            time.sleep(2)
                            break
                        #StdOut('.')
                        printf('.',log=self.log,direct=True,log_level=1)
                        time.sleep(1)
                #Turn on 
                cmd='on'
            if cmd == 'on':
                json_cmd='On'
            elif cmd == 'off':
                json_cmd='ForceOff'
            elif cmd == 'shutdown':
                json_cmd='GracefulShutdown'
            elif cmd == 'reset':
                json_cmd='ForceRestart'
            elif cmd == 'reboot':
                json_cmd='GracefulRestart'
            rt=self.Post('/Systems/1/Actions/ComputerSystem.Reset',json={'Action': 'Reset', 'ResetType': json_cmd})
            if cmd in ['on','reset','reboot'] and sensor_up > 0:
                return self.IsUp(timeout=timeout,keep_up=sensor_up)
            elif cmd in ['off','shutdown'] and sensor_down > 0:
                return self.IsDown(timeout=timeout,keep_down=sensor_down)
            else:
                Time=TIME()
                while True:
                    if Time.Out(timeout): return False
                    if cmd_state(cmd,on_s=['reset','on','reboot','off_on']) == get_current_power_state().lower():
                        time.sleep(1)
                        return True
                    #StdOut(self.power_unknown_tag)
                    printf(self.power_unknown_tag,log=self.log,direct=True,log_level=1)
                    time.sleep(3)
                return False
        else:
            if cmd == 'info':
                naa={}
                ok,aa=self.Get('Managers/1/Oem/Supermicro/SmartPower')
                if not ok:
                    silent_status_log: printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1)
                    return naa
                if isinstance(aa,dict):
                    naa['status']=aa.get('PowerStatus')
                    naa['max']=aa.get('MaxPower')
                    naa['cap']=aa.get('PowerCapping')
                ok,aa=self.Get('Chassis/1/Power')
                if not ok:
                    printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1)
                    return naa
                if isinstance(aa,dict):
                    naa['psu']={}
                    if aa.get('PowerControl'):
                        interval='{}m'.format(aa.get('PowerControl')[0].get('PowerMetrics',{}).get('IntervalInMin'))
                        naa['psu'][interval]={}
                        #naa['psu']['cap']=aa.get('PowerControl')[0].get('PowerCapacityWatts')
                        #naa['psu']['output']=aa.get('PowerControl')[0].get('PowerConsumedWatts')
                        naa['psu'][interval]['max']=aa.get('PowerControl')[0].get('PowerMetrics',{}).get('MaxConsumedWatts')
                        naa['psu'][interval]['min']=aa.get('PowerControl')[0].get('PowerMetrics',{}).get('MinConsumedWatts')
                        naa['psu'][interval]['avg']=aa.get('PowerControl')[0].get('PowerMetrics',{}).get('AverageConsumedWatts')
                    for psu in aa.get('PowerSupplies'):
                        idx=psu.get('MemberId')
                        naa['psu'][idx]={}
                        naa['psu'][idx]['model']=psu.get('Model')
                        naa['psu'][idx]['watt']=psu.get('PowerCapacityWatts')
                        naa['psu'][idx]['output']=psu.get('LastPowerOutputWatts')
                        naa['psu'][idx]['firmware']=psu.get('FirmwareVersion')
                        naa['psu'][idx]['sn']=psu.get('SerialNumber')
                        naa['psu'][idx]['type']=psu.get('PowerSupplyType')
                        naa['psu'][idx]['health']=psu.get('Status',{}).get('Health')
                        input_source=psu.get('LineInputVoltageType')
                        input_volt=psu.get('LineInputVoltage')
                        if input_source=='Unknown':
                            input_source=input_source+'(Maybe unpluged cable)'
                        else:
                            input_source=input_source+'({}V)'.format(input_volt)
                        naa['psu'][idx]['input']=input_source
                return naa
            elif cmd == 'ID_LED':
                ok,aa=self.Get('Chassis/1')
                if not ok:
                    printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1)
                    return naa
                if isinstance(aa,dict):
                    return aa.get('IndicatorLED')
    
    def Boot(self,boot=None,mode='auto',keep='once',simple_mode=False,pxe_boot_mac=None,force=False,set_bios_uefi=False):
        # mode : auto will default set to UEFI
        #TODO: Setup iPXE
        # - bios mode is UEFI and order[0] is not PXE then, setup boot order to UEFI mode PXE
        #   if not then try again with ipmitool's boot order to iPXE
        #   until set to want mode
        def SMC_OEM_SPECIAL_BOOTORDER(next_pxe_id=False):
            #if it has multiplue PXE bootable mac then try next pxe boot id when next_pxe_id=# (int number)
            #B13
            naa={}
            ok,aa=self.Get('Systems/1/Oem/Supermicro/FixedBootOrder')
            if not ok or not isinstance(aa,dict):
                return False
            naa['mode']=aa.get('BootModeSelected')
            pxe_boot_mac=[]
            for i in aa.get('UEFINetwork'):
                for x in i.split():
                    a=MacV4(x)
                    if a and a not in pxe_boot_mac:
                        pxe_boot_mac.append(a)
            naa['order']=aa.get('FixedBootOrder')
            for i in range(0,len(naa['order'])):
                if isinstance(next_pxe_id,int) and not isinstance(next_pxe_id,bool) and next_pxe_id >= i:
                    continue

                for x in naa['order'][i].split():
                    a=MacV4(x)
                    if a and a in pxe_boot_mac:
                        naa['pxe_boot_id']=i
                        naa['pxe_boot_mac']=a
                        break
            return naa

        def order_boot():
            #Get Bootorder information
            naa={}
            ok,aa=self.Get('Systems/1')
            if not ok or not isinstance(aa,dict):
                printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1)
                naa['error']=aa
                return naa
            boot_info=aa.get('Boot',{})
            if boot_info:
                naa['mode']=boot_info.get('BootSourceOverrideMode')
                naa['1']=boot_info.get('BootSourceOverrideTarget')
                naa['enable']=boot_info.get('BootSourceOverrideEnabled')
                naa['help']={}
                if 'BootSourceOverrideMode@Redfish.AllowableValues' in boot_info: naa['help']['mode']=boot_info.get('BootSourceOverrideMode@Redfish.AllowableValues')
                if 'BootSourceOverrideTarget@Redfish.AllowableValues' in boot_info: naa['help']['boot']=boot_info.get('BootSourceOverrideTarget@Redfish.AllowableValues')
            return naa

        def bios_boot(pxe_boot_mac=None,next_pxe_id=False):
            # Try to Special OEM BOOT ORDER first
            naa=SMC_OEM_SPECIAL_BOOTORDER(next_pxe_id=next_pxe_id)
            if isinstance(naa,dict): return naa
            #Get BIOS Boot order information
            naa={}
            ok,bios_info=self.Get('Systems/1/Bios')
            if not ok or not isinstance(bios_info,dict):
                printf('Redfish ERROR: {}'.format(bios_info),log=self.log,log_level=1)
                naa['error']=bios_info
                return naa
            #PXE Boot Mac
            if pxe_boot_mac is None: pxe_boot_mac=self.BaseMac().get('lan')
            naa['pxe_boot_mac']=MacV4(pxe_boot_mac)
            #Boot order
            boot_attr=bios_info.get('Attributes',{})
            if boot_attr:
                mode=None
                #Need update for H13, X13, B13, B2 information
                if 'BootModeSelect' in boot_attr: #X12
                    mode=boot_attr.get('BootModeSelect')
                elif 'Bootmodeselect' in boot_attr: #X11
                    mode=boot_attr.get('Bootmodeselect')
                elif 'BootSourceOverrideMode' in boot_attr:
                    mode=boot_attr.get('BootSourceOverrideMode')
                if IsNone(mode): #X13
                    #VideoOptionROM
                    for ii in boot_attr:
                        if ii.startswith('OnboardVideoOptionROM#'):
                            naa['OnboardVideoOptionROM']=boot_attr[ii]
                    #Boot order
                    ok,aa=self.Get('Systems/1/BootOptions')
                    if not ok:
                        printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1)
                        naa['error']=aa
                        return naa
                    if isinstance(aa,dict):
                        memb=aa.get('Members',[{}])
                        if len(memb) == 1:
                            naa['mode']='Legacy'
                            naa['order']=['']
                            naa['pxe_boot_id']=None
                        else:
                            naa['mode']='UEFI'
                            naa['order']=[]
                            for mem_id in memb:
                                redirect=mem_id.get('@odata.id')
                                if isinstance(redirect,str) and redirect:
                                    ok,aa=self.Get(redirect)
                                    if not ok:
                                        printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1)
                                        naa['error']=aa
                                        return naa
                                    if isinstance(aa,dict):
                                        if 'UEFI Network Card' in aa.get('DisplayName','') or 'UEFI PXE IP' in aa.get('DisplayName',''):
                                            naa['order'].append('UEFI PXE Network: UEFI')
                                            a=FIND(aa.get('DisplayName')).Find("(MAC:\w+)")
                                            if a:
                                                mac=MacV4(a[0][4:] if isinstance(a,list) else a[4:] if isinstance(a,str) else a)
                                                if naa.get('pxe_boot_id') is None and mac == naa['pxe_boot_mac']:
                                                    naa['pxe_boot_id']=len(naa['order'])-1
                                                    break
                                        else:
                                            naa['order'].append(aa.get('DisplayName',''))
                else: #X12
                    #VideoOptionROM
                    naa['OnboardVideoOptionROM']=bios_info.get('OnboardVideoOptionROM')
                    naa['mode']=mode
                    #Boot order
                    naa['order']=[]
                    bios_boot_info=list(boot_attr.items())
                    for i in range(0,len(bios_boot_info)):
                        if bios_boot_info[i][0].startswith('BootOption'):
                            naa['order'].append(bios_boot_info[i][1])
                            a=FIND(bios_boot_info[i][1]).Find("(MAC:\w+)")
                            if a:
                                mac=MacV4(a[0][4:] if isinstance(a,list) else a[4:] if isinstance(a,str) else a)
                                if naa.get('pxe_boot_id') is None and mac == naa['pxe_boot_mac']:
                                    naa['pxe_boot_id']=len(naa['order'])-1
                                    break
            return naa

        def SetBootOrder(boot,mode='auto',keep='Once',pxe_boot_mac=None,force=False):
            #Set Bootorder after turn off system
            def CheckBootInfo(rf_boot_info,boot,mode,keep):
                # Check current BIOS and Bootorder status is same as want value
                boot_order_enable=rf_boot_info.get('order',{}).get('enable','')
                # according to BIOS CFG Boot
                if boot_order_enable == 'Disabled':
                    if mode == rf_boot_info.get('bios',{}).get('mode','') or (mode=='Legacy' and rf_boot_info.get('bios',{}).get('mode','') == 'Dual') or (mode == 'UEFI' and rf_boot_info.get('bios',{}).get('mode','') == 'Dual'):
                        bios_first_boot_order_string=Get(rf_boot_info.get('bios',{}).get('order',[]),0,default='')
                        if mode=='UEFI':
                            if (boot == 'Pxe' and 'UEFI PXE' in bios_first_boot_order_string) or (boot.upper() in bios_first_boot_order_string):
                                printf('Redfish: Already Same condition(1) with {}, {}, {}'.format(mode,boot, keep),log=self.log,log_level=6)
                                return True,'[redfish] Already Same condition(1) with {}, {}, {}'.format(mode,boot, keep)
                        elif mode == 'Legacy':
                            if (boot == 'Pxe' and 'Network:IBA' in bios_first_boot_order_string) or (boot.upper() in bios_first_boot_order_string):
                                printf('Redfish: Already Same condition(2) with {}, {}, {}'.format(mode,boot, keep),log=self.log,log_level=6)
                                return True,'[redfish] Already Same condition(2) with {}, {}, {}'.format(mode,boot, keep)
                # according to Bootorder
                elif boot_order_enable == 'Continuous':
                    if rf_boot_info.get('order',{}).get('1','') == boot=='Pxe' and mode == rf_boot_info.get('order',{}).get('mode'):
                        printf('Redfish: Already Same condition(3) with {}, {}, {}'.format(mode,boot, keep),log=self.log,log_level=6)
                        return True,'[redfish] Already Same condition(3) with {}, {}, {}'.format(mode,boot,keep)
                return None,None


            rf_boot_info={'order':order_boot(),'bios':bios_boot(pxe_boot_mac=pxe_boot_mac)}
            if not rf_boot_info['order'] and not rf_boot_info['bios']:
                #Redfish issue
                return False,'Redfish Issue'
            # Change keep,mode,boot parameter to Redfish's parameter name
            if IsIn(boot,['efi_shell','uefi_shell','shell']):
                keep='Continuous'
                mode='UEFI'
                boot='BiosSetup'
            else:
                #New Setup    
                ## Mode
                if IsIn(boot,['ipxe','uefi','efi']) or IsIn(mode,['uefi','efi','ipxe']):
                    boot='Pxe'
                    mode='UEFI'
                elif IsIn(mode,['legacy','dual']):
                    mode='Legacy'
                else: # auto then 
                    mode=rf_boot_info.get('bios',{}).get('mode')
                    if IsNone(mode) or IsIn(mode,['Dual']): mode='Legacy'

                ## Keep
                if IsIn(keep,[None,False,'disable','del','disabled']):
                    keep='Disabled'
                elif IsIn(keep,['keep','continue','force','continuous']):
                    keep='Continuous'
                else:
                    keep='Once'

                ##  boot
                if IsIn(boot,['pxe']):
                    boot='Pxe'
                elif IsIn(boot,['cd']):
                    boot='Cd'
                elif IsIn(boot,['usb']):
                    boot='Usb'
                elif IsIn(boot,['hdd']):
                    boot='Hdd'
                elif IsIn(boot,['floppy']):
                    boot='Floppy'
                elif IsIn(boot,['bios','setup','biossetup']):
                    mode='Legacy'
                    boot='BiosSetup'
                    keep='Once'
                #########################################
                #Check Already got same condition
                if not force:
                    ok,msg=CheckBootInfo(rf_boot_info,boot,mode,keep)
                    if ok:
                        return ok,msg

            #Setup required power condition off for Redfish
            pw=self.Power()
            if pw != 'off':
                for i in range(0,5):
                    if self.Power(cmd='off',sensor_up=3):
                        pw='off'
                        break
                    printf('.',log=self.log,direct=True,log_level=1)
                    time.sleep(10)
            if pw != 'off':
                printf('.',no_intro=True,log=self.log,log_level=1,scr_dbg=False)
                return False,'Power off fail in SetBiosBootmode()'
            #Set bootorder mode
            boot_db={'Boot':{
                 'BootSourceOverrideEnabled':keep,
                 'BootSourceOverrideMode':mode,
                 'BootSourceOverrideTarget':boot
                 }
            }
            rc=False
            rc_msg='[redfish] Can not set to {},{},{}'.format(mode,boot, keep)
            for i in range(0,3):
                rc=self.Post('Systems/1',json=boot_db,mode='patch')
                if rc:
                
                    for j in range(0,100):
                        time.sleep(10)
                        chk={'order':order_boot(),'bios':bios_boot(pxe_boot_mac=pxe_boot_mac)}
                        ok,msg=CheckBootInfo(chk,boot,mode,keep)
                        if ok:
                            rc_msg='[redfish] Set to {},{},{}'.format(mode,boot, keep)
                            rc=True
                            break
                        else:
                            rc_msg='[redfish] Can not find {},{},{} config'.format(mode,boot, keep)
                            rc=False
                        time.sleep(5)
                        printf('.',log=self.log,direct=True,log_level=1)
                    break
                else:
                    #Try Power On and off for Redfish error
                    self.Power(cmd='on',sensor_up=5)
                    self.Power(cmd='off',sensor_up=5)
                    time.sleep(5)
                    printf('.',log=self.log,direct=True,log_level=1)
            printf('.',no_intro=True,log=self.log,log_level=1)
            printf('{}'.format(rc_msg),log=self.log,log_level=6)
            return rc,rc_msg

        if isinstance(mode,str) and isinstance(boot,str) and boot.lower() in ['efi_shell','uefi_shell','shell','pxe','ipxe','cd','usb','hdd','floppy','bios','setup','biossetup','efi','uefi','set']:
            if set_bios_uefi and IsIn(boot,['uefi','efi','ipxe']) and IsIn(mode,['auto','uefi_bootmode','uefi','efi']):
                ok,rm=self.SetBiosBootmode(mode='UEFI',force=force) # Set to UEFI Bootmode in BIOS CFG
                if ok: # Set to UEFI Bootmode in BIOS CFG
                    return True,'Set UEFI Mode with PXE Boot order in BIOS CFG'
                if 'Not licensed to perform' in rm:
                    return False,rm
                return ok,rm
            return SetBootOrder(boot,mode,keep,pxe_boot_mac,force)
        else:
            if IsIn(simple_mode,[True,'simple']):
                bios_boot_info=bios_boot(pxe_boot_mac=pxe_boot_mac)
                if 'error' in bios_boot_info: return bios_boot_info.get('error')
                if bios_boot_info: return True,bios_boot_info.get('mode')
            elif IsIn(simple_mode,['bios']):
                #return True,bios_boot(pxe_boot_mac=pxe_boot_mac)
                bbrc=bios_boot(pxe_boot_mac=pxe_boot_mac)
                return True,bbrc
            elif IsIn(simple_mode,['order']):
                return True,order_boot()
            elif IsIn(simple_mode,['flags']):
                naa={'order':order_boot(),'bios':bios_boot(pxe_boot_mac=pxe_boot_mac)}
                return True,'''Boot Flags :
   - BIOS {} boot
   - BIOS PXE Boot order : {}
   - Options apply to {}
   - Boot Device Selector : {}
   - Boot with {}
'''.format(naa.get('bios',{}).get('mode'),naa.get('bios',{}).get('pxe_boot_id'),'all future boots' if naa.get('order',{}).get('enable') == 'Continuous' else naa.get('order',{}).get('enable'),naa.get('order',{}).get('1'),naa.get('order',{}).get('mode'))
            else: #all
                naa={'order':order_boot(),'bios':bios_boot(pxe_boot_mac=pxe_boot_mac)}
                if isinstance(boot,str) and boot.lower() == 'order':
                    return True,'''Boot Flags :
   - BIOS {} boot
   - BIOS PXE Boot order : {}
   - Options apply to {}
   - Boot Device Selector : {}
   - Boot with {}
'''.format(naa.get('bios',{}).get('mode'),naa.get('bios',{}).get('pxe_boot_id'),'all future boots' if naa.get('order',{}).get('enable') == 'Continuous' else naa.get('order',{}).get('enable'),naa.get('order',{}).get('1'),naa.get('order',{}).get('mode'))
                return True,naa

    def SetBiosBootmode(self,mode='UEFI',power='auto',power_timeout=300,monitor_timeout=600,force=False):
        #Setup Bios Bootmode after turn off the system(Redfish)
        #Setting BIOS Boot Mode : UEFI, Legacy, Dual
        if mode not in ['UEFI','Legacy','Dual']: return False
        ok,bios_boot_mode=self.Boot(simple_mode='bios')
        if not ok:
            return False,bios_boot_mode
        if force is False and bios_boot_mode.get('mode') == mode and bios_boot_mode.get('pxe_boot_id') == 0:
            return True,'[redfish] Already UEFI Mode with PXE Boot order in BIOS CFG'
        ok,rc=self.Get("Systems/1/Bios")
        if not ok:
            printf('Redfish ERROR: {}'.format(rc),log=self.log,log_level=1)
            return False,rc
        if not isinstance(rc,dict): return False
        setting_cmd=rc.get('@Redfish.Settings',{}).get('SettingsObject',{}).get('@odata.id')
        if setting_cmd:
            if 'BootModeSelect' in rc.get('Attributes',{}): #X12 & H12
                boot_mode_name='BootModeSelect'
            elif 'Bootmodeselect' in rc.get('Attributes',{}): #X11
                boot_mode_name='Bootmodeselect'
            else:
                #Need update for H13, X13, B13, B2 information
                #Not found Boot mode select name in BIOS
                return False,'Unknown BIOS Bootmode'

            #Setup required power condition off for Redfish
            pw=self.Power()
            if pw != 'off':
                for i in range(0,5):
                    if self.Power(cmd='off',sensor_up=3):
                        pw='off'
                        break
                    printf('.',log=self.log,direct=True,log_level=1)
                    time.sleep(10)
            if pw != 'off':
                printf('.',log=self.log,no_intro=True,log_level=1,scr_dbg=False)
                return False,'Power off fail in SetBiosBootmode()'

            aa={'Attributes': {boot_mode_name: mode}}
            if self.Post(setting_cmd,json=aa,mode='patch'):
                time.sleep(10)
                tok,tbios_boot_mode=self.Boot(simple_mode='bios')
                printf('.',log=self.log,no_intro=True,log_level=1,scr_dbg=False)
                if tbios_boot_mode.get('mode') == mode and tbios_boot_mode.get('pxe_boot_id') == 0:
                    return True,'[redfish] Set UEFI Mode with PXE Boot order in BIOS CFG'
                return False,'[redfish] Can not set UEFI Bios Mode with PXE Boot order in BIOS CFG'
            else:
                printf('.',log=self.log,no_intro=True,log_level=1,scr_dbg=False)
                return False,'[redfish] Can not set UEFI Bios Mode'
        printf('.',log=self.log,no_intro=True,log_level=1,scr_dbg=False)
        return False,'Unkown redfish power command'

    def SystemReadySensor(self):
        ok,aa=self.Get('Chassis/1/Thermal')
        if not ok:
            printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1)
            return False
        if isinstance(aa,dict):
            rc=False
            for ii in aa.get('Temperatures',[]):
                if ii.get('PhysicalContext') == 'CPU':
                    rc=None
                    try:
                        return int(ii.get('ReadingCelsius'))
                    except:
                        pass
            #If Redfish find CPU then return None(power down)
            #If not found CPU then return to False(Error)
            return rc
        return False
        
    def IsUp(self,timeout=600,keep_up=0):
        up_init=None
        Time=TIME()
        while True:
            if Time.Out(timeout): break
            stat=self.power_unknown_tag
            cpu_temp=self.SystemReadySensor()
            if cpu_temp is False: return False
            if cpu_temp in ['up']:
                if keep_up > 0:
                    if up_init is None: up_init=TIME()
                    if up_init.Out(keep_up): return True
                    stat=self.power_on_tag
                else:
                    return True
            else:
                stat=self.power_off_tag
            #StdOut(stat)
            printf(stat,direct=True,log=self.log,log_level=1)
            time.sleep(3)
        return False

    def IsDown(self,timeout=300,keep_down=0):
        dn_init=None
        Time=TIME()
        while True:
            if Time.Out(timeout): break
            stat=self.power_unknown_tag
            cpu_temp=self.SystemReadySensor()
            if cpu_temp is False: return False
            if cpu_temp in ['up']:
                stat=self.power_on_tag
            else:
                if keep_down > 0:
                    if dn_init is None: dn_init=TIME()
                    if dn_init.Out(keep_down): return True
                    stat=self.power_off_tag
                else:
                    return True
            #StdOut(stat)
            printf(stat,direct=True,log=self.log,log_level=1)
            time.sleep(3)
        return False

    def BmcVer(self):
        ok,aa=self.Get('UpdateService/FirmwareInventory/BMC')
        if not ok:
            printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1)
            return None
        if isinstance(aa,dict): return aa.get('Version')
        ok,aa=self.Get('Managers/1')
        if not ok:
            printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1)
            return None
        if isinstance(aa,dict): return aa.get('FirmwareVersion')

    def BiosVer(self):
        ok,aa=self.Get('UpdateService/FirmwareInventory/BIOS')
        if not ok:
            printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1)
            return None
        if isinstance(aa,dict): return aa.get('Version')
        ok,aa=self.Get('Systems/1')
        if not ok:
            printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1)
            return None
        if isinstance(aa,dict): return aa.get('BiosVersion')

    def RedfishHI(self):
        naa={}
        ok,aa=self.Get('Systems/1/EthernetInterfaces/ToManager')
        if isinstance(aa,dict):
            ipv4=aa.get('IPv4Addresses',[{}])[0]
            naa['ip']=ipv4.get('Address')
            naa['netmask']=ipv4.get('SubnetMask')
            naa['gateway']=ipv4.get('Gateway')
            naa['type']=ipv4.get('AddressOrigin')
            naa['mtu']=aa.get('MTUSize')
            naa['full_duplex']=aa.get('FullDuplex')
            naa['auto']=aa.get('AutoNeg')
            naa['speed']=aa.get('SpeedMbps')
            naa['mac']=aa.get('PermanentMACAddress')
            naa['enable']=aa.get('InterfaceEnabled')
            #naa['status']=aa.get('Status',{}).get('Health')
            naa['status']=aa.get('Status',{}).get('State')
        return naa

    def BaseMac(self,port=None):
        naa={}
        ok,aa=self.Get('Managers/1')
        if not ok:
            printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1)
            return naa
        if isinstance(aa,dict):
            naa['bmc']=MacV4(aa.get('UUID').split('-')[-1])
        naa['lan']=self.PXEMAC()
        if not naa['lan']:
            ok,aa=self.Get('Systems/1')
            if not ok:
                printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1)
                return naa
            if isinstance(aa,dict):
                naa['lan']=MacV4(aa.get('UUID').split('-')[-1])
            if naa.get('lan') and naa['lan'] == naa.get('bmc'):
                rf_net=self.Network()
                for nid in rf_net:
                    for pp in rf_net[nid].get('port',{}):
                        port_state=rf_net[nid]['port'][pp].get('state')
                        if port:
                            if '{}'.format(port) == '{}'.format(pp):
                                naa['lan']=rf_net[nid]['port'][pp].get('mac')
                                break
                        elif isinstance(port_state,str) and port_state.lower() == 'up':
                            naa['lan']=rf_net[nid]['port'][pp].get('mac')
                            break
        return naa 

    def Network(self):
        naa={}
        ok,aa=self.Get('Chassis/1/NetworkAdapters')
        if not ok:
            printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1)
            return naa
        if isinstance(aa,dict):
            for ii in aa.get('Members',[]):
                ok,ai=self.Get(ii.get('@odata.id'))
                if not ok:
                    printf('Redfish ERROR: {}'.format(ai),log=self.log,log_level=1)
                    return naa
                if isinstance(ai,dict):
                    ai_id=ai.get('Id')
                    naa[ai_id]={}
                    naa[ai_id]['model']=ai.get('Model')
                    naa[ai_id]['sn']=ai.get('SerialNumber')
                    if ai.get('Controllers'):
                        naa[ai_id]['firmware']=ai.get('Controllers')[0].get('FirmwarePackageVersion')
                        naa[ai_id]['pci']='{}({})'.format(ai.get('Controllers')[0].get('PCIeInterface',{}).get('PCIeType'),ai.get('Controllers')[0].get('PCIeInterface',{}).get('LanesInUse'))
                        naa[ai_id]['max_pci']='{}({})'.format(ai.get('Controllers')[0].get('PCIeInterface',{}).get('MaxPCIeType'),ai.get('Controllers')[0].get('PCIeInterface',{}).get('MaxLanes'))
                        naa[ai_id]['location']='{}'.format(ai.get('Controllers')[0].get('Location',{}).get('PartLocation',{}).get('LocationOrdinalValue'))
                    naa[ai_id]['port']={}
                    ok,port=self.Get(ai.get('NetworkPorts').get('@odata.id'))
                    if not ok:
                        printf('Redfish ERROR: {}'.format(port),log=self.log,log_level=1)
                        return naa
                    if isinstance(port,dict):
                        for pp in port.get('Members'):
                            ok,port_q=self.Get(pp.get('@odata.id'))
                            if not ok:
                               printf('Redfish ERROR: {}'.format(port_q),log=self.log,log_level=1)
                               return naa
                            naa[ai_id]['port'][port_q.get('Id')]={}
                            naa[ai_id]['port'][port_q.get('Id')]['mac']=port_q.get('AssociatedNetworkAddresses')[0]
                            naa[ai_id]['port'][port_q.get('Id')]['state']=port_q.get('LinkStatus')
        return naa

    def PXEMAC(self):
        #if it has multiplue PXE bootable mac then try next pxe boot id when next_pxe_id=# (int number)
        #B13
        ok,aa=self.Get('Systems/1/Oem/Supermicro/FixedBootOrder')
        if ok and isinstance(aa,dict):
            for i in aa.get('UEFINetwork'):
                for x in i.split():
                    a=MacV4(x)
                    return a
        #Normal system case
        ok,aa=self.Get('Systems/1')
        if not ok or not isinstance(aa,dict):
            printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1)
            return False
        rf_key=aa.get('EthernetInterfaces',{}).get('@odata.id')
        if rf_key:
            ok,aa=self.Get(rf_key)
            if ok and isinstance(aa,dict):
                rf_key=aa.get('Members',[{}])[0].get('@odata.id')
                if rf_key:
                    ok,aa=self.Get(rf_key)
                    if ok and isinstance(aa,dict):
                        return MacV4(aa.get('MACAddress'))
        
    def Memory(self):
        naa={}
        ok,aa=self.Get('Systems/1/Memory')
        if not ok:
            printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1)
            return naa
        if isinstance(aa,dict):
            for ii in aa.get('Members',[]):
                ok,ai=self.Get(ii.get('@odata.id'))
                if not ok:
                    printf('Redfish ERROR: {}'.format(ai),log=self.log,log_level=1)
                    return naa
                if isinstance(ai,dict):
                    idx=ai.get('Id')
                    naa[idx]={}
                    naa[idx]['dimm']=ai.get('DeviceLocator')
                    naa[idx]['speed']=ai.get('AllowedSpeedsMHz')[0]
                    naa[idx]['size']=ai.get('LogicalSizeMiB')
                    naa[idx]['ecc']=ai.get('ErrorCorrection')
                    naa[idx]['brand']=ai.get('Manufacturer')
                    naa[idx]['partnumber']=ai.get('PartNumber')
                    naa[idx]['sn']=ai.get('SerialNumber')
        return naa

    def Cpu(self):
        naa={}
        ok,aa=self.Get('Systems/1/Processors')
        if not ok:
            printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1)
            return naa
        if isinstance(aa,dict):
            for ii in aa.get('Members',[]):
                ok,ai=self.Get(ii.get('@odata.id'))
                if not ok:
                    printf('Redfish ERROR: {}'.format(ai),log=self.log,log_level=1)
                    return naa
                if isinstance(ai,dict):
                    idx=ai.get('Id')
                    naa[idx]={}
                    naa[idx]['watt']=ai.get('MaxTDPWatts')
                    naa[idx]['type']=ai.get('Location',{}).get('PartLocation',{}).get('LocationType')
                    naa[idx]['location']=ai.get('Location',{}).get('PartLocation',{}).get('ServiceLabel')
                    naa[idx]['model']=ai.get('Model')
                    naa[idx]['speed']=ai.get('MaxSpeedMHz')
                    naa[idx]['step']=ai.get('ProcessorId',{}).get('Step')
                    naa[idx]['cores']=ai.get('TotalCores')
        return naa

    def Info(self):
        naa={}
        naa['version']={'bios':self.BiosVer(),'bmc':self.BmcVer()}
        naa['network']=self.Network()
        naa['redfish']=self.IsEnabled()
        naa['redfish_hi']=self.RedfishHI()
        naa['power']=self.Power('info')
        naa['memory']=self.Memory()
        naa['cpu']=self.Cpu()
        ok,aa=self.Get('Managers/1')
        if not ok:
            printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1)
            return naa
        naa['mac']={}
        if isinstance(aa,dict):
            naa['mac']['bmc']=MacV4(aa.get('UUID').split('-')[-1])
        ok,aa=self.Get('Systems/1')
        if not ok:
            printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1)
            return naa
        if isinstance(aa,dict):
            naa['mac']['lan']=MacV4(aa.get('UUID').split('-')[-1])
            naa['Model']=aa.get('Model')
            naa['SerialNumber']=aa.get('SerialNumber')
            naa['UUID']=aa.get('UUID')
        ok,aa=self.Get('Chassis/1')
        if not ok:
            printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1)
            return naa
        if isinstance(aa,dict):
            manufacturer=aa.get('Manufacturer')
            naa['manufacturer']=manufacturer
            naa['boardid']=aa.get('Oem',{}).get(manufacturer,{}).get('BoardID')
            naa['sn']=aa.get('Oem',{}).get(manufacturer,{}).get('BoardSerialNumber')
            naa['guid']=aa.get('Oem',{}).get(manufacturer,{}).get('GUID')
        naa['bootmode']=self.Boot()[1]
        naa['console']=self.ConsoleInfo()
        return naa

    def BiosPassword(self,new,old=''):
        #Not perfectly work now
        passwd_db={
            'PasswordName':'AdminPassword',
            'OldPassword':old,
            'NewPassword':new,
        }
        return self.Post('Systems/1/Bios/Actions/Bios.ChangePassword',json=passwd_db)

    def FactoryDefaultBios(self):
        return self.Post('Systems/1/Bios/Actions/Bios.ResetBios')

    def VirtualMedia(self,mode='floppy'):
        mode=mode.lower()
        info=[]
        ok,vv=self.Get('Managers/1/VirtualMedia')
        if not ok:
            printf('Redfish ERROR: {}'.format(vv),log=self.log,log_level=1)
            return False
        if isinstance(vv,dict):
            for ii in vv.get('Members',[]):
                redfish_path=None
                if mode == 'floppy' and os.path.basename(ii.get('@odata.id')).startswith('Floppy'):
                    redfish_path=ii.get('@odata.id')
                elif mode == 'cd' and os.path.basename(ii.get('@odata.id')).startswith('CD'):
                    redfish_path=ii.get('@odata.id')
                elif mode == 'all':
                    redfish_path=ii.get('@odata.id')
                if redfish_path:
                    ok,aa=self.Get(redfish_path)
                    if not ok:
                        printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1)
                        return False
                    if aa:
                        if aa.get('Inserted'):
                            if aa.get('ConnectedVia') == 'URI':
                                info.append('SUM:{}'.format(aa.get('Id')))
                            elif aa.get('ConnectedVia') == 'Applet':
                                info.append('KVM:{}'.format(aa.get('Id')))
        if info:
            return ','.join(info)
        return False

    def IsEnabled(self,timeout=10):
        old=TIME().Int()
        while TIME().Int() - old < timeout:
            ok,aa=self.Get('Systems')
            if not ok:
                printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1)
                return False
            if not isinstance(aa,dict):
                #StdOut('.')
                printf('.',direct=True,log=self.log,log_level=1)
                time.sleep(1)
                continue
            else:
                return True
        return False

    def iKVM(self,mode=None):
        rf_key='/Managers/1/Oem/Supermicro/IKVM'
        for i in range(0,2):
            aa=self.Get(rf_key)
            if aa[0]:
                if aa[1].get('Current interface') == 'HTML 5':
                    if mode == 'url':
                        return True,'https://{}/{}'.format(self.host,aa[1].get('URI'))
                    else:
                        import webbrowser
                        webbrowser.open_new('https://{}/{}'.format(self.host,aa[1].get('URI')))
                        return True,'ok'
                else:
                    if not self.Post(rf_key,json={'Current interface':'HTML 5'},mode='patch'):
                        return False,'Can not set to HTML 5'
            else:
                rf_key='/Managers/1/IKVM'
        return False,'Can not login to the server'

    def ConsoleInfo(self):
        aa=self.Get('Systems/1')
        out={}
        if aa[0]:
            for ii in aa[1].get('SerialConsole'):
                if ii not in out: out[ii]={}
                for jj in aa[1]['SerialConsole'][ii]:
                    if jj in ['Port','ServiceEnabled']:
                        out[ii][jj]=aa[1]['SerialConsole'][ii][jj]
            gpc=aa[1].get('GraphicalConsole')
            if gpc:
                out[gpc.get('ConnectTypesSupported')[0]]={'Port':gpc.get('Port'),'ServiceEnabled':gpc.get('ServiceEnabled')}
        return out

    def McResetCold(self):
        return self.Post('/Managers/1/Actions/Manager.Reset')

class kBmc:
    def __init__(self,*inps,**opts):
        self.find_user_passwd_with_redfish=opts.get('find_user_passwd_with_redfish',False)
        self.power_on_tag='¯'
        self.power_up_tag='∸'
        self.power_off_tag='_'
        self.power_down_tag='⨪'
        self.power_unknown_tag='·'
        env=Get(inps,0) if Get(inps,0,err=True) else Get(opts,['ip','ipmi_ip'],default=None,err=True,peel='force')
        if isinstance(env,dict):
            if opts: env.update(opts)
            opts=env
            self.ip=Get(opts,['ip','ipmi_ip'],default=None,err=True,peel='force')
        else:
            self.ip=env
        self.user=Get(inps,1) if Get(inps,1,err=True) else Get(opts,['user','ipmi_user'],default='ADMIN',err=True,peel='force')
        self.passwd=Get(inps,2) if Get(inps,2,err=True) else Get(opts,['password','passwd','ipmi_pass'],default='ADMIN',err=True,peel='force')
        self.port=Get(opts,['port','ipmi_port'],default=(623,664,443),err=True,peel='force')
        Get(opts,['port','ipmi_port'],default=(623,664,443),err=True,peel='force')
        self.mac=Get(opts,['mac','ipmi_mac','bmc_mac'],default=None,err=True,peel='force')
        self.upasswd=Get(opts,['ipmi_upass','upasswd'],default=None,err=True,peel='force')
        self.eth_mac=opts.get('eth_mac')
        self.eth_ip=opts.get('eth_ip')
        self.err={}
        self.warning={}
        self.canceling={}
        self.cancel_func=opts.get('cancel_func',opts.get('stop_func',None))
        self.bgpm={}
        self.mac2ip=opts.get('mac2ip',None)
        self.log=opts.get('log',None)
        self.org_user=opts.get('org_user',self.user)
        self.default_passwd=opts.get('default_passwd')
        self.org_passwd=opts.get('org_passwd',self.passwd)
        self.test_user=opts.get('test_user')
        if not self.test_user: self.test_user=['ADMIN','Admin','admin','root','Administrator']
        self.base_passwd=['ADMIN','Admin','admin','root','Administrator']
        self.test_passwd=opts.get('test_pass',opts.get('test_passwd',self.base_passwd))
        if self.user in self.test_user: self.test_user.remove(self.user)
        if self.passwd in self.test_passwd: self.test_passwd.remove(self.passwd)
        self.cmd_module=[Ipmitool()]
        if opts.get('cmd_module') and isinstance(opts.get('cmd_module'),list):
            self.cmd_module=opts.get('cmd_module')
        if opts.get('smc_file') and os.path.isfile(opts.get('smc_file')):
            if isinstance(self.cmd_module,list):
                self.cmd_module.append(Smcipmitool(smc_file=opts.get('smc_file')))
            else:
                self.cmd_module=[Ipmitool(),Smcipmitool(smc_file=opts.get('smc_file'))]

        self.log_level=opts.get('log_level',5)
        if self.log is None:
            global printf_log_base
            printf_log_base=6
            global printf_caller_detail
            global printf_caller_tree
        self.timeout=opts.get('timeout',1800)
        self.checked_ip=False
        self.checked_port=False
        self.org_ip='{}'.format(self.ip)
        # Redfish Support
        self.redfish=opts.get('redfish') if isinstance(opts.get('redfish'),bool) else True if opts.get('redfish_hi') is True else None
        rf=None
        if self.redfish is None:
            rf=self.CallRedfish(True,True)
            self.redfish=rf.IsEnabled() if rf else False
        if self.redfish:
            # If support Redfish then check redfish_hi interface
            if isinstance(opts.get('redfish_hi'),bool):
                self.redfish_hi=opts.get('redfish_hi')
            else:
                if rf is None: rf=self.CallRedfish(True,True)
                self.redfish_hi=rf.RedfishHI().get('enable') if rf else False
        else:
            self.redfish_hi=False
        self.power_monitor_stop=False
        self.power_get_redfish=opts.get('power_get_redfish',True)
        self.power_get_sensor=opts.get('power_get_sensor',True)
        self.power_get_tools=opts.get('power_get_tools',True)

    def CallRedfish(self,force=False,check=True,no_ipmitool=False):
        if self.redfish or force:
            if check:
                ip=self.mac2ip(self.mac) if self.mac2ip and self.checked_ip is False and MacV4(self.mac) else '{}'.format(self.ip)
                ping_rc=ping(ip,keep_good=0,timeout=self.timeout,log=self.log,cancel_func=self.cancel_func)
                if ping_rc is True:
                    self.checked_ip=True
                    cc=False
                    for i in range(0,10):
                        if IpV4(ip,port=self.port):
                            cc=True
                            break
                        printf(".",log=self.log,direct=True)
                        time.sleep(3)
                    if cc is False:
                    #if not IpV4(ip,port=self.port):
                        printf('.',no_intro=True,log=self.log)
                        self.error(_type='ip',msg="{} is not IPMI IP(1)".format(ip))
                        printf("{} is not IPMI IP(1)".format(ip),log=self.log,log_level=1,dsp='e')
                        return False
                    ok=False
                    if not no_ipmitool:
                        ok,user,passwd=self.find_user_pass(ip,no_redfish=True)
                    if ok:
                        return Redfish(host=ip,user=user,passwd=passwd,log=self.log)
                    else:
                        test_user=MoveData(self.test_user[:],self.user,to='first')
                        if not test_user: test_user=['ADMIN']
                        test_passwd=self.test_passwd[:]
                        test_passwd=MoveData(test_passwd,test_passwd[-1],to='first') # move last one
                        if self.upasswd: test_passwd=MoveData(test_passwd,self.upasswd,to='first') # move uniq passwd
                        if self.default_passwd : test_passwd=MoveData(test_passwd,self.default_passwd,to='first') # move default  passwd
                        if self.org_passwd: test_passwd=MoveData(test_passwd,self.org_passwd,to='first') # move original passwd
                        test_passwd=MoveData(test_passwd,self.passwd,to='first') # move current passwd
                        printf("Search User and Password in Redfish",log=self.log,mode='d')
                        for i_user in test_user:
                            for i in range(0,len(test_passwd)):
                                rf=Redfish(host=ip,user=i_user,passwd=test_passwd[i],log=self.log)
                                aa=rf.Get('/Systems')
                                if krc(aa,chk=True):
                                    printf('.',no_intro=True,log=self.log)
                                    printf("Found Redfish Login User&Password: {},{}".format(i_user,test_passwd[i]),log=self.log,log_level=1,mode='d')
                                    return rf
                                printf(".",direct=True,log=self.log)
                                if i > 1 and i+1 % 2 == 0:
                                    time.sleep(50)
                                else:
                                    time.sleep(1)
                        printf("Can not find Redfish working user/password",log=self.log,log_level=1,dsp='w')
                else:
                    printf("Can not ping to {}".format(ip),log=self.log,log_level=1,dsp='e')
                    self.error(_type='ip',msg="Can not ping to {}".format(ip))
                printf(".",log=self.log,log_level=1,no_intro=True,scr_dbg=False)
                return False
            else:
                return Redfish(host=self.ip,user=self.user,passwd=self.passwd,log=self.log)
        printf(".",log=self.log,log_level=1,no_intro=True,scr_dbg=False)
        return False

    def SystemReadySensor(self,cmd_str,name):
        #ipmitool/smcipmitool's cpu temperature
        rrc=self.run_cmd(cmd_str)
        if krc(rrc[0],chk=True):
            for ii in rrc[1][1].split('\n'):
                ii_a=ii.split('|')
                find=''
                if name == 'smc' and len(ii_a) > 2:
                    find=ii_a[1].strip().upper()
                elif len(ii_a) > 5:
                    find=ii_a[0].strip().upper()
                else:
                    continue
                if '_' not in find and 'TEMP' in find and ('CPU' in find or 'SYSTEM ' in find):
                    if name == 'smc':
                        tmp=ii_a[2].strip()
                        if tmp in ['N/A','Disabled','0C/32F']:
                            return 'down'
                        elif 'C/' in tmp and 'F' in tmp: # Up state
                            return 'up'
                        elif tmp == 'No Reading':
                            self.warn(_type='sensor',msg="Can not read sensor data")
                    else: #ipmitool
                        tmp=ii_a[3].strip()
                        tmp2=ii_a[4].strip()
                        if tmp == 'ok':
                            return 'up'
                        elif tmp == 'na':
                            if tmp2 == 'na': #Add H13 rule
                                return 'down'
                            else:
                                try:
                                    int(float(tmp2))
                                    return 'down'
                                except:
                                    pass
        #Check Redfish again
        rf=self.CallRedfish()
        if rf:
            cpu_temp=rf.SystemReadySensor()
            if cpu_temp is False: return 'error'
            if isinstance(cpu_temp,int): return 'up'
            return 'down'
        elif rf is 0:
            return 'cancel'
        return 'unknown'

    def power_get_status(self,redfish=None,sensor=None,tools=None,**opts):
        if redfish is None: redfish=self.power_get_redfish
        if sensor is None: sensor=self.power_get_sensor
        if tools is None: tools=self.power_get_tools

        # _: Down, ¯: Up, ·: Unknown sensor data, !: ipmi sensor command error
        out=['none','none','none'] # [Sensor(ipmitool/SMCIPMITool), Redfish, ipmitool/SMCIPMITool]
        if redfish:
            rf=self.CallRedfish()
            if rf:
                rt=rf.Power(cmd='status')
                if IsIn(rt,['on','off']):
                    out[1]=rt
        if tools:
            for mm in self.cmd_module:
                rt=self.run_cmd(mm.cmd_str('ipmi power status',passwd=self.passwd))
                if krc(rt,chk=True):
                    aa=rt[1][1].split()[-1]
                    if isinstance(aa,str) and aa.lower() in ['on','off']:
                        out[2]=aa
                        break
        if sensor:
            for mm in self.cmd_module:
                rt=self.SystemReadySensor(mm.cmd_str('ipmi sensor',passwd=self.passwd),mm.__name__)
                out[0]='on' if rt == 'up' else 'off' if rt == 'down' else rt
                break 
        return out

    # Map for threading function
    def power_status_monitor_t(self,monitor_status,data={},keep_off=0,keep_on=0,sensor_on=600,sensor_off=0,monitor_interval=5,timeout=1200,reset_after_unknown=0,mode='s'):
        return self.power_status_monitor(monitoring_state=monitor_status,data=data,keep_off=keep_off,keep_on=keep_on,sensor_on=sensor_on,sensor_off=sensor_off,status_log=False,monitor_interval=monitor_interval,timeout=timeout,reset_after_unknown=reset_after_unknown,mode=mode)

    def power_status_monitor(self,monitoring_state=None,data=None,**opts):
        if not monitoring_state and 'monitor_status' in opts: monitoring_state=opts.get('monitor_status')
        if not monitoring_state: return False,'not found monitoring_state value'
        if data is None and 'data' in opts: data=opts['data']
        if not isinstance(data,dict): return False,'data parameter value format is wrong'
        ############################
        #Default values parameters
        #define get power status function
        get_current_power_status=opts.get('get_current_power_status')
        if IsNone(get_current_power_status): get_current_power_status=self.power_get_status
        status_log=opts.get('status_log',True)
        monitor_interval=Int(opts.get('monitor_interval'),5)
        timeout=Int(opts.get('timeout'),1800)
        reset_after_unknown=Int(opts.get('reset_after_unknown'),0)
        sensor_off_time=Int(opts.get('sensor_off_time',opts.get('sensor_on')),600)
        mode=opts.get('mode','a')
        info=opts.get('info',False)
        # monitoring_state= list or string with comma (monitoring each state step)
        # timeout : monitoring timeout
        # monitor_interval : monitoring interval time
        # sensor_off_time  : after this time return redfish and ipmitool command result when mode is sensor and not changed the sensor data
        # keep_last_state_time : last monitoring time(keep the same state (time) of last monitoring)
        # mode : s:sensor, a:any data, r: redfish data, t: ipmitool data
        # data['done_reason']='Reason Tag (ok/stop/cancel/error/timeout)'
        # status_log : True: Print on screen, False: not print on screen
        # get_current_power_status : function, if none then use power_get_status()
        # info : True:print summary when finish, False: not print

        #### define local varible
        # count : how many loop
        # printed : fix printing 
        def is_on_off(data,mode='a',sensor_time=None,sensor_off_time=420):
            # data: [Sensor data(ipmitool/smcipmitool), Redfish data, ipmitool/smcipmitool data)]
            if data[0] == data[1] and data[1] == data[2]: # All same data then return without any condition
                return data[0],0
            if mode == 's':
                if not sensor_time: sensor_time=TIME().Int()
                if data[1] == data[2] and data[1] == 'off':
                    return 'off',sensor_time
                elif data[0] == 'off':
                    # over 7min(420) then use redfish and ipmitool command result
                    if isinstance(sensor_time,int) and sensor_time:
                        if TIME().Int()-sensor_time > sensor_off_time:
                            if data[1] == data[2]: # redfish and ipmitool has same result then cmd result
                                return data[1],sensor_time
                            else:
                                # one of command got unknown then the other result
                                if data[1] == 'unknown' and data[2] in ['on','off']:
                                    return data[2],sensor_time
                                elif data[2] == 'unknown' and data[1] in ['on','off']:
                                    return data[1],sensor_time
                    return 'off',sensor_time
            elif mode == 'a':
                if 'on' in data[1:]: return 'on',0 # anyone on then on 
                if 'off' in data[1:]: return 'off',0  # anyone off then off
            elif mode == 'r':
                if data[1] in ['on','off']: return data[1],0 # redfish output
            else:
                if data[2] in ['on','off']: return data[2],0 # cmd output
            return 'unknown',0

        def mark_on_off(a):
            if isinstance(a,str) and a.lower() in ['on','up']:
                return 'on'
            elif isinstance(a,str) and a.lower() in ['off','down','shutdown']:
                return 'off'

        if isinstance(monitoring_state,str):
            monitoring_state=monitoring_state.split(',')
        for i in range(0,len(monitoring_state)-1):
            b=mark_on_off(monitoring_state[i])
            if isinstance(b,str):
                monitoring_state[i]=b

        ##########
        if 'keep_on' in opts and monitoring_state[-1] == 'on':
            keep_last_state_time=Int(opts.get('keep_on'),0)
        elif 'keep_off' in opts and monitoring_state[-1] == 'off':
            keep_last_state_time=Int(opts.get('keep_off'),0)
        else:
            keep_last_state_time=Int(opts.get('keep_last_state_time'),0)

        #########################################
        #initialize data
        #########################################
        if not isinstance(data,dict): data={}
        if 'count' not in data: data['count']=0
        if 'stop' not in data: data['stop']=False
        if 'timeout' not in data: data['timeout']=timeout # default 1800(30min)
        if 'sensor_off_time' not in data: data['sensor_off_time']=Int(sensor_off_time,450) # Sensor monitoring timeout 
        if 'monitor_interval' not in data: data['monitor_interval']=Int(monitor_interval,5) # default 5
        if 'keep_last_state_time' not in data: data['keep_last_state_time']=Int(keep_last_state_time,0)
        if 'mode' not in data: data['mode']=mode if mode in ['s','a','r','t'] else 'a'
        #data monitoring initialize data (time, status)
        if 'init' not in data: data['init']={}
        if 'config' not in data['init']: data['init']['config']={'time':TIME().Int(),'status':get_current_power_status()}
        data['monitoring']=monitoring_state # want monitoring state
        data['monitored_status']={}
        before=None
        monitor_id=0
        monitoring_start_time=None
        monitoring_state=None
        data['remain_time']=data.get('timeout')
        is_on_off_time=None
        Time=TIME()
        ss=''
        while True:
            data['count']+=1
            if data['init'].get('start',{}).get('time'):
                data['remain_time']=data.get('timeout') - (TIME().Int() - data['init'].get('config',{}).get('time'))
            if not 'start' in data.get('init',{}) and data.get('start') is True:
                #Start monitoring initialize data (time, status)
                #we can check time and status condition between defined bpm time and start monitoring
                data['init']['start']={'time':TIME().Int(),'status':get_current_power_status()}
            # Timeout
            if Time.Out(data['timeout']):
                data['done']={TIME().Int():'Monitoring timeout({}sec)'.format(data['timeout'])}
                data['done_reason']='timeout'
                if status_log:
                    printf('.',log=self.log,no_intro=True,log_level=1)
                return
            #manually stop condition (Need this condition at any time)
            elif data.get('stop') is True or IsBreak(data.get('cancel_func')):
                if IsBreak(data.get('cancel_func')):
                    data['done']={TIME().Int():'Got Cancel Signal during monitor {}{}'.format('_'.join(data['monitoring']),ss)}
                    data['done_reason']='cancel'
                else:
                    data['done']={TIME().Int():'Got STOP Signal during monitor {}{}'.format('_'.join(data['monitoring']),ss)}
                    data['done_reason']='stop'
                if 'worker' in data: data.pop('worker')
                if status_log:
                    printf('.',no_intro=True,log=self.log,log_level=1)
                return
            # just wait unit get start
            if not 'start' in data.get('init',{}):
                time.sleep(1)
                continue
            ############################################
            # Monitoring condition
            ############################################
            ## monitoring current condition (convert to defined mode(on/off/unknown) only)
            on_off,is_on_off_time=is_on_off(get_current_power_status(),mode=data['mode'],sensor_time=is_on_off_time,sensor_off_time=data['sensor_off_time'])
            if on_off not in data['monitored_status']: data['monitored_status'][on_off]=[]
            if monitoring_state == on_off:
                data['monitored_status'][on_off][-1]['keep_time']=TIME().Int()
            else:
                btime=TIME().Int()
                data['monitored_status'][on_off].append({'time':btime,'keep_time':btime})
                monitoring_state=on_off
                monitoring_start_time=TIME().Int()
                is_on_off_time=None
                if on_off in ['on','off']: ss=ss+'-{}'.format(on_off) if ss else on_off
            ############################################
            #Design for status printing
            if on_off == 'on':
                if status_log:
                    printf(self.power_on_tag,log=self.log,direct=True,log_level=1)
                data['symbol']=self.power_on_tag
            elif on_off == 'off':
                if monitoring_state == 'on' and len(data['monitoring'])-1 == monitor_id:
                    if status_log:
                        printf('+',log=self.log,direct=True,log_level=1)
                    data['symbol']='+'
                else:
                    if status_log:
                        printf(self.power_off_tag,log=self.log,direct=True,log_level=1)
                    data['symbol']=self.power_off_tag
            elif on_off == 'up':
                if status_log:
                    printf(bmc.power_up_tag,log=bmc.log,direct=True,log_level=1)
                data['symbol']=bmc.power_up_tag
            elif on_off == 'dn':
                if status_log:
                    printf(bmc.power_down_tag,log=bmc.log,direct=True,log_level=1)
                data['symbol']=bmc.power_down_tag
            else:
                if status_log:
                    printf(self.power_unknown_tag,log=self.log,direct=True,log_level=1)
                data['symbol']=self.power_unknown_tag
            ################################################
            # if same condition then add to monitored status(Next step monitoring)
            if on_off == data['monitoring'][monitor_id]:
                if monitor_id < len(data['monitoring'])-1: monitor_id+=1
            ############################################
            #Done Break condition
            if len(data['monitoring'])-1 == monitor_id and data['monitoring'][monitor_id] in data['monitored_status']:
                if monitor_id > 0:
                    #multi status monitor
                    if data['monitored_status'][data['monitoring'][monitor_id]][-1].get('time') <= data['monitored_status'][data['monitoring'][monitor_id-1]][-1].get('keep_time'):
                        #wrong monitored ordering
                        time.sleep(monitor_interval) # monitoring interval
                        continue
                if data['keep_last_state_time'] == 0: # just meet condition
                     data['repeat']=len(data['monitored_status'][data['monitoring'][monitor_id]])-1
                     data['done']={TIME().Int():ss}
                     data['done_reason']='ok'
                     break
                else:
                     # keep condition-time condition
                     if data['monitored_status'][data['monitoring'][monitor_id]][-1].get('keep_time') - data['monitored_status'][data['monitoring'][monitor_id]][-1].get('time') >= data['keep_last_state_time']:
                         data['repeat']=len(data['monitored_status'][data['monitoring'][monitor_id]])-1
                         data['done']={TIME().Int():ss}
                         data['done_reason']='ok'
                         break
            time.sleep(monitor_interval) # monitoring interval

        if 'worker' in data: data.pop('worker')
        # end of status printing condition
        if status_log:
            printf('',log=self.log,no_intro=True,log_level=1)
        # convert monitored_status to searial ordering
        A={}
        for i in data['monitored_status']:
            for j in data['monitored_status'][i]:
                A[j.get('time')]={i:j}
        B=[]
        data['monitored_order']=[]
        for i in sorted(A.items()):
            B.append(i[1])
            data['monitored_order'].append(next(iter(i[1])))
        # Summary print condition
        if status_log and info is True:

            data_info='Monitor Start at {} with {}'.format(data['init']['start']['time'],data['monitoring'])
            for i in B:
                i_name=next(iter(i))
                data_info=data_info+'\n{} detected at {} ({}sec)'.format(i_name,i.get(i_name).get('time'),i.get(i_name).get('keep_time')-i.get(i_name).get('time'))
            data_info=data_info+'\nkeep time of last state  : {}'.format(data.get('keep_last_state_time'))
            data_info=data_info+'\nFinished time  : {}'.format(next(iter(data.get('done'))))
            data_info=data_info+'\nFinished Reason: {} ({})'.format(data.get('done_reason'),data.get('done')[next(iter(data.get('done')))])
            printf(data_info,log=bmc.log,log_level=1)

    def power_monitor(self,timeout=1200,monitor_status=['off','on'],keep_off=0,keep_on=0,sensor_on_monitor=600,sensor_off_monitor=0,monitor_interval=5,reset_after_unknown=0,start=True,background=False,status_log=False,**opts):
        #timeout       : monitoring timeout
        #monitor_status: monitoring status off -> on : ['off','on'], on : ['on'], off:['off']
        #keep_off: off state keeping time : 0: detected then accept
        #keep_on : on state keeping time : 0: detected then accept, 30: detected and keep same condition during 30 seconds then accept
        #sensor_on_monitor: First Temperature sensor data(cpu start) monitor time, if passed this time then use ipmitool's power status data(on)
        #sensor_off_monitor: First Temperature sensor data(not good) monitor time, if passed this time then use ipmitool's power status(off)
        #status_log: True : print out on screen, if background = True then it will automatically False
        #background: ready at background process
        # - start: True : monitoring start, False : just waiting monitoring
        # - rt['start']=True: if background monitor was False and I want start monitoring then give it to True
        # - rt['stop']=True : Stop monitoring process
        timeout=timeout if isinstance(timeout,int) else 1200
        if not opts.get('mode'):
            if sensor_on_monitor or sensor_off_monitor:
                opts['mode']='s'
            else:
                opts['mode']='a'
        if background is True:
            #Background, it wait until start acition.
            # wait until action start
            # if start action then keep monitoring.
            # Background monitoring only single times
            #self.bgpm['timeout']=timeout
            #self.bgpm['start']=start
            # Block duplicated running
            if self.bgpm.get('worker') and self.bgpm['worker'].isAlive():
                print('Already running')
                return self.bgpm
            # if new monitoring then initialize data
            self.bgpm={'status':{},'repeat':0,'stop':False,'count':0,'start':start,'timeout':timeout,'cancel_func':self.cancel_func}
            #self.bgpm['worker']=threading.Thread(target=self.power_status_monitor,args=(monitor_status,self.bgpm,self.power_get_status,keep_off,keep_on,sensor_on_monitor,sensor_off_monitor,False,monitor_interval,timeout,0))
            self.bgpm['worker']=threading.Thread(target=self.power_status_monitor_t,args=(monitor_status,self.bgpm,keep_off,keep_on,sensor_on_monitor,sensor_off_monitor,monitor_interval,timeout,0,opts.get('mode','a')))
            self.bgpm['worker'].start()
            return self.bgpm
        else:
            #foreground should be different
            #act foreground then immediately start monitoring and return the output
            fgpm={'status':{},'repeat':0,'stop':False,'count':0,'start':True,'timeout':1800,'cancel_func':self.cancel_func}
            self.power_status_monitor(monitor_status,fgpm,keep_off=keep_off,keep_on=keep_on,sensor_monitor=sensor_on_monitor,sensor_off_monitor=sensor_off_monitor,status_log=status_log,monitor_interval=monitor_interval,timeout=timeout,reset_after_unknown=reset_after_unknown,mode=opts.get('mode','a'))
            return fgpm

    def check(self,mac2ip=None,cancel_func=None,trace=False,timeout=None):
        if cancel_func is None: cancel_func=self.cancel_func
        if timeout is None: timeout=self.timeout
        chk=False
        ip='{}'.format(self.ip)
        for i in range(0,2):
            if self.checked_ip is False:
                if mac2ip and self.mac:
                    ip=mac2ip(self.mac)
                    chk=True
                    self.checked_port=False
            ping_rc=ping(ip,keep_good=0,timeout=timeout,log=self.log,cancel_func=cancel_func)
            if ping_rc is True:
                if self.checked_port is False:
                    if IpV4(ip,port=self.port):
                        self.checked_port=True
                    else:
                        cc=False
                        for i in range(0,10):
                            if IpV4(ip,port=self.port):
                                self.checked_port=True
                                cc=True
                                break
                            printf(".",log=self.log,direct=True)
                            time.sleep(3)
                        if cc is False:
                            printf(".",no_intro=True,log=self.log,log_level=1)
                            printf("{} is not IPMI IP(2)".format(ip),log=self.log,log_level=1,dsp='e')
                            self.error(_type='ip',msg="{} is not IPMI IP(2)".format(ip))
                            return False,self.ip,self.user,self.passwd
                self.checked_ip=True
                ok,user,passwd=self.find_user_pass(ip,trace=trace,cancel_func=cancel_func)
                if ok:
                    if chk:
                        mac=self.get_mac(ip,user=user,passwd=passwd)
                        if mac != self.mac:
                            printf(".",no_intro=True,log=self.log,log_level=1,scr_dbg=False)
                            self.error(_type='ip',msg='Can not find correct IPMI IP')
                            printf("Can not find correct IPMI IP",log=self.log,log_level=1,mode='e')
                            return False,self.ip,self.user,self.passwd
                    #Update IP,User,Password
                    if self.ip != ip:
                        printf(".",no_intro=True,log=self.log,log_level=1,scr_dbg=False)
                        printf('Update IP from {} to {}'.format(ip,self.ip),log=self.log,log_level=1,dsp='e')
                        self.ip=ip
                    if self.user != user:
                        printf(".",no_intro=True,log=self.log,log_level=1,scr_dbg=False)
                        printf('Update User from {} to {}'.format(user,self.user),log=self.log,log_level=1,dsp='e')
                        self.user=user
                    if self.passwd!= passwd:
                        printf(".",no_intro=True,log=self.log,log_level=1,scr_dbg=False)
                        printf('Update Password from {} to {}'.format(passwd,self.passwd),log=self.log,log_level=1,dsp='e')
                        self.passwd=passwd
                    return True,ip,user,passwd
                else:
                    printf(".",no_intro=True,log=self.log,log_level=1)
                    printf('Can not check password with ipmitool, So return global infomation',log=self.log,dsp='d')
                    return True,ip,self.user,self.passwd
            self.checked_ip=False
        printf(".",no_intro=True,log=self.log,log_level=1)
        self.checked_ip=True
        self.error(_type='net',msg='Destination Host({}) Unreachable/Network problem'.format(ip))
        printf(ip,log=self.log,log_level=1,dsp='e')
        return False,self.ip,self.user,self.passwd

    def get_cmd_module_name(self,name):
        if isinstance(self.cmd_module,list):
            for mm in self.cmd_module:
                if Type(mm,('classobj','instance')) and IsSame(mm.__name__,name):
                    if mm.ready:
                        return mm,'Found'
                    else:
                        if mm.__name == 'ipmitool':
                            lmmsg='Please install ipmitool package!!'
                            printf(lmmsg,log=self.log,log_level=1,dsp='e')
                        elif mm.smc_file:
                            lmmsg='SMCIPMITool file ({}) not found!!'.format(mm.smc_file)
                            printf(lmmsg,log=self.log,log_level=1,dsp='e')
                        else:
                            lmmsg='NOT defined SMCIPMITool file parameter'
                        return False,lmmsg
            return None,'not defined module {}'.format(name)
        printf('wrong cmd_module',log=self.log,log_level=1,dsp='e')
        return None,'wrong cmd_module'

    def find_uefi_legacy(self,bioscfg=None): # Get UEFI or Regacy mode
        def aa(a):
            if isinstance(a,list):
                if len(a)==1: return a[0]
                return ''
            return a

        def xml_find(data):
            onboard_video_rom=[]
            selected_option=[]
            default_option=[]
            first_option=[]
            count=0
            for i in range(0,len(data)):
                if '<Menu name="Boot">' in data[i]:
                    for j in range(i,len(data)):
                        if '<Setting name="Boot Mode Select"' in data[j]:
                            selected_option=re.compile('<Setting name="Boot Mode Select" selectedOption="(\w.*)" type="Option">').findall(data[j])
                            count+=1
                        elif not default_option and selected_option and '<DefaultOption>' in data[j]:
                            default_option=re.compile('<DefaultOption>(\w.*)</DefaultOption>').findall(data[j])
                            count+=1
                        elif '<Setting name="Boot Option #1" order="1"' in data[j]:
                            first_option=re.compile('<Setting name="Boot Option #1" order="1" selectedOption="(\w.*)" type="Option">').findall(data[j])
                            if first_option:
                                if 'EFI Network:' in first_option[0]:
                                    first_option='IPXE'
                                elif 'Network:' in first_option[0]:
                                    first_option='PXE'
                            count+=1
#                        elif selected_option and '</Setting>' in data[j]:
#                            break
                elif '<Setting name="Onboard Video Option ROM" selectedOption' in data[i]:
                    onboard_video_rom=re.compile(r'<Setting name=\"Onboard Video Option ROM\" selectedOption=\"(\w.*)\" type=\"Option\">').findall(data[i])
                    count+=1
                if count >= 4:
                    return aa(selected_option),aa(default_option),aa(first_option),aa(onboard_video_rom)
        def flat_find(data):
            for i in range(0,len(data)):
                if '[Boot]' in data[i]:
                    for j in range(i,len(data)):
                        if data[j].strip().startswith('Boot Mode Select'):
                            sop=data[j].strip().split()[2].split('=')[1]
                            if sop == '02':
                                return 'DUAL','','',''
                            elif sop == '01':
                                return 'UEFI','','',''
                            elif sop == '01':
                                return 'LEGACY','','',''

        def find_boot_mode(data):
            data_a=data.split('\n')
            for i in range(0,len(data_a)):
                if '<?xml version' in data_a[i]:
                    return xml_find(data_a[i:])
                elif '[Advanced' in data_a[i]:
                    return flat_find(data_a[i:])

        # Boot mode can automatically convert iPXE or PXE function
        # if power handle command in here then use bmc.power(xxxx,lanmode=self.bmc_lanmode) code
        if isinstance(bioscfg,str):
            if os.path.isfile(bioscfg):
                with open(bioscfg,'rb') as f:
                    bioscfg=f.read()
        if isinstance(bioscfg,str) and bioscfg:
            found=find_boot_mode(Str(bioscfg))
            if found:
                return True,found
        return False,('','','','')

    def find_user_pass(self,ip=None,default_range=12,check_cmd='ipmi power status',cancel_func=None,error=True,trace=False,extra_test_user=[],extra_test_pass=[],no_redfish=False,first_user=None,first_passwd=None):
        if cancel_func is None: cancel_func=self.cancel_func
        if ip is None: ip=self.ip
        if not IpV4(ip): return False,None,None
        test_user=MoveData(self.test_user[:],self.user,to='first')
        if not test_user: test_user=['ADMIN']
        if 'ADMIN' not in test_user: test_user=['ADMIN']+test_user
        if isinstance(first_user,str) and first_user: test_user=MoveData(test_user[:],first_user,to='first')
        if extra_test_user and isinstance(extra_test_user,list): test_user=test_user+extra_test_user
        test_passwd=self.test_passwd[:]
        if 'ADMIN' not in test_passwd: test_passwd=['ADMIN']+test_passwd
        if extra_test_pass and isinstance(extra_test_pass,list): test_passwd=test_passwd+extra_test_pass
        test_passwd=MoveData(test_passwd,test_passwd[-1],to='first') # move last one
        if self.upasswd: test_passwd=MoveData(test_passwd,self.upasswd,to='first') # move uniq passwd
        if self.org_passwd: test_passwd=MoveData(test_passwd,self.org_passwd,to='first') # move original passwd
        if self.default_passwd and self.default_passwd not in test_passwd: test_passwd=[self.default_passwd]+test_passwd
        test_passwd=MoveData(test_passwd,self.passwd,to='first') # move current passwd
        if isinstance(first_passwd,str) and first_passwd:
            test_passwd=MoveData(test_passwd,first_passwd,to='first') # move current passwd
#        for i in self.base_passwd: # Append base password
#            if i not in test_passwd: test_passwd.append(i)
        tt=1
        #if len(self.test_passwd) > default_range: tt=2
        tt=(len(test_passwd) // default_range) + 1
        tested_user_pass=[]
        print_msg=False

        for mm in self.cmd_module:
            for t in range(0,tt):
                if t == 0:
                    #test_pass_sample=self.test_passwd[:default_range]
                    test_pass_sample=test_passwd[:default_range]
                else:
                    #test_pass_sample=self.test_passwd[default_range:]
                    test_pass_sample=test_passwd[default_range*t:default_range*(t+1)]
                # Two times check for uniq,current,temporary password
                #if self.upasswd: test_pass_sample=MoveData(test_pass_sample[:],self.upasswd,to='first')
                #if self.org_passwd: test_pass_sample=MoveData(test_pass_sample[:],self.org_passwd,to='first')
                #test_pass_sample=MoveData(test_pass_sample,self.passwd,to='first')
                #if self.default_passwd not in test_pass_sample: test_pass_sample.append(self.default_passwd)
                for uu in test_user:
                    #If user is None then skip
                    if IsNone(uu): continue
                    for pp in test_pass_sample:
                        #If password is None then skip
                        if IsNone(pp): continue
                        #Check ping first before try password
                        ping_rc=ping(ip,keep_good=0,timeout=self.timeout,log=self.log,cancel_func=cancel_func) # Timeout :kBmc defined timeout(default:30min), count:1, just pass when pinging
                        if ping_rc is True:
                            tested_user_pass.append((uu,pp))
                            cmd_str=mm.cmd_str(check_cmd,passwd=pp)
                            full_str=cmd_str[1]['base'].format(ip=ip,user=uu,passwd=pp)+' '+cmd_str[1]['cmd']
                            rc=rshell(full_str)
                            chk_user_pass=False
                            if rc[0] in cmd_str[3]['ok']:
                                chk_user_pass=True
                            elif rc[0] == 1:
                                # Some of BMC version return code 1, but works. So checkup output string too
                                if 'Chassis Power is' in rc[1]:
                                    chk_user_pass=True
                                # IPMITOOL Failed then try with Redfish
                                elif self.find_user_passwd_with_redfish and self.redfish: #Redfish will lock bmc user when many times failed login
                                    rf=Redfish(host=ip,user=uu,passwd=pp)
                                    if IsIn(rf.Power(cmd='status',silent_status_log=True),['on','off']):
                                        chk_user_pass=True
                            if chk_user_pass:
                                #Found Password. 
                                if self.user != uu: #If changed user
                                    printf('.',log=self.log,no_intro=True)
                                    printf("""[BMC]Found New User({})""".format(uu),log=self.log,log_level=3)
                                    self.user=uu
                                if self.passwd != pp: #If changed password
                                    printf('.',log=self.log,no_intro=True)
                                    printf("""[BMC]Found New Password({})""".format(pp),log=self.log,log_level=3)
                                    self.passwd=pp
                                return True,uu,pp
                            else:
                                #If not found current password then try next
                                if not print_msg:
                                    printf('.',log=self.log,no_intro=True)
                                    printf("""Check BMC USER and PASSWORD from the POOL:""",direct=True,log=self.log,log_level=3)
                                    print_msg=True
                                if self.log_level < 7 and not trace:
                                    printf("""p""",log=self.log,direct=True,log_level=3)
                                else:
                                    printf('.',log=self.log,no_intro=True)
                                    printf("""Try BMC User({}) and password({}), But failed. test next one\n""".format(uu,pp),direct=True,log=self.log,log_level=3)
                                time.sleep(1) # make to some slow check for BMC locking
                                #time.sleep(0.4)
                        else:
                            # Ping error or timeout
                            printf('.',log=self.log,no_intro=True)
                            printf("""WARN: Can not ping to the destination IP({})""".format(ip),log=self.log,log_level=1,dsp='e')
                            if error:
                                self.error(_type='ip',msg="Can not ping to the destination IP({})".format(ip))
                            return False,None,None
                    if self.log_level < 7 and not trace:
                        printf("""u""",log=self.log,direct=True,log_level=3)
                    #maybe reduce affect to BMC
                    time.sleep(1)
        #Whole tested but can not find
        # Reset BMC and try again
        printf(""".""",log=self.log,no_intro=True)
        printf("""no_redfish:{}""".format(no_redfish),log=self.log,dsp='d')
        if not no_redfish:
            printf("""Try McResetCold and try again""",log=self.log,dsp='d')
            if self.McResetCold(ip,no_ipmitool=True): # Block Loop
                return self.find_user_pass(ip=ip,default_range=default_range,check_cmd=check_cmd,cancel_func=cancel_func,error=error,trace=trace,no_redfish=True)
        printf("""WARN: Can not find working BMC User or password from POOL\n{}""".format(tested_user_pass),log=self.log,log_level=1,dsp='e')
        if error:
            self.error(_type='user_pass',msg="Can not find working BMC User or password from POOL\n{}".format(tested_user_pass))
        return False,None,None

    def McResetCold(self,ip=None,no_ipmitool=False):
        printf("""Reboot BMC""",log=self.log,log_level=1,dsp='d')
        rf=self.CallRedfish(no_ipmitool=no_ipmitool)
        if rf:
            if rf.McResetCold():
                printf("""Wait until response from BMC""",log=self.log,log_level=1,dsp='d')
                if not ip : ip=self.ip
                return ping(ip,keep_good=10,timeout=self.timeout,cancel_func=self.cancel_func,log=self.log)
            else:
                printf("""Try with ipmitool(1)""",log=self.log,log_level=1,dsp='d')
                if self.reset(cancel_func=self.cancel_func):
                    if not ip : ip=self.ip
                    return ping(ip,keep_good=10,timeout=self.timeout,cancel_func=self.cancel_func,log=self.log)
                else:
                    printf("""E: Can not reset the BMC""",log=self.log,log_level=1,dsp='d')
        else:
            printf("""Try with ipmitool(2)""",log=self.log,log_level=1,dsp='d')
            if self.reset(cancel_func=self.cancel_func):
                if not ip : ip=self.ip
                return ping(ip,keep_good=10,timeout=self.timeout,cancel_func=self.cancel_func,log=self.log)
            else:
                printf("""E: Can not initialize Redfish""",log=self.log,log_level=1,dsp='d')
        return False

    def recover_user_pass(self):
        mm,msg=self.get_cmd_module_name('smc')
        if not mm:
            return False,msg,None
        was_user='''{}'''.format(self.user)
        was_passwd='''{}'''.format(self.passwd)
        ok,user,passwd=self.find_user_pass()
        if ok:
            printf("""Previous User({}), Password({}). Found available current User({}), Password({})\n****** Start recovering user/password from current available user/password......\n""".format(was_user,was_passwd,user,passwd),log=self.log,log_level=3)
        else:
            return False,'Can not find current available user and password',None
        if user == self.org_user:
            if passwd == self.org_passwd:
                printf("""Same user and passwrd. Do not need recover""",log=self.log,log_level=4)
                return True,user,passwd
            else:
                #SMCIPMITool.jar IP ID PASS user setpwd 2 <New Pass>
                recover_cmd=mm.cmd_str("""user setpwd 2 {}""".format(FixApostrophe(self.org_passwd)))
        else:
            #SMCIPMITool.jar IP ID PASS user add 2 <New User> <New Pass> 4
            recover_cmd=mm.cmd_str("""user add 2 {} {} 4""".format(self.org_user,FixApostrophe(self.org_passwd)))
        printf("""Recover command: {}""".format(recover_cmd),log_level=7)
        rc=self.run_cmd(recover_cmd)

        if krc(rc[0],chk='error'):
            printf("""BMC Password: Recover fail""",log=self.log,log_level=1)
            self.warn(_type='ipmi_user',msg="BMC Password: Recover fail")
            return 'error',user,passwd
        if krc(rc[0],chk=True):
            printf("""Recovered BMC: from User({}) and Password({}) to User({}) and Password({})""".format(user,passwd,self.org_user,self.org_passwd),log=self.log,log_level=4)
            ok2,user2,passwd2=self.find_user_pass()
            if ok2:
                printf("""Confirmed changed user password to {}:{}""".format(user2,passwd2),log=self.log,log_level=4)
            else:
                return False,"Looks changed command was ok. but can not found acceptable user or password"
            self.user='{}'.format(user2)
            self.passwd='{}'.format(passwd2)
            return True,self.user,self.passwd
        else:
            printf("""Not support {}. Looks need more length. So Try again with {}""".format(self.org_passwd,self.default_passwd),log=self.log,log_level=4)
            if self.user == self.org_user:
                #SMCIPMITool.jar IP ID PASS user setpwd 2 <New Pass>
                recover_cmd=mm.cmd_str("""user setpwd 2 {}""".format(FixApostrophe(self.default_passwd)))
            else:
                #SMCIPMITool.jar IP ID PASS user add 2 <New User> <New Pass> 4
                recover_cmd=mm.cmd_str("""user add 2 {} {} 4""".format(self.org_user,FixApostrophe(self.default_passwd)))
        #    print('\n*kBMC2: {}'.format(recover_cmd))
            printf("""Recover command: {}""".format(recover_cmd),log_level=7)
            rrc=self.run_cmd(recover_cmd)
            if krc(rrc[0],chk=True):
                printf("""Recovered BMC: from User({}) and Password({}) to User({}) and Password({})""".format(self.user,self.passwd,self.org_user,self.default_passwd),log=self.log,log_level=4)
                ok2,user2,passwd2=self.find_user_pass()
                if ok2:
                    printf("""Confirmed changed user password to {}:{}""".format(user2,passwd2),log=self.log,log_level=4)
                else:
                    return False,"Looks changed command was ok. but can not found acceptable user or password",None
                self.user='''{}'''.format(user2)
                self.passwd='''{}'''.format(passwd2)
                return True,self.user,self.passwd
            else:
                self.warn(_type='ipmi_user',msg="Recover ERROR!! Please checkup user-lock-mode on the BMC Configure.")
                printf("""BMC Password: Recover ERROR!! Please checkup user-lock-mode on the BMC Configure.""",log=self.log,log_level=1)
                return False,self.user,self.passwd

    def run_cmd(self,cmd,append=None,path=None,retry=0,timeout=None,return_code={'ok':[0,True],'fail':[]},show_str=False,dbg=False,mode='app',cancel_func=None,peeling=False,progress=False,ip=None,user=None,passwd=None,cd=False,keep_cwd=False,check_password_rc=[],trace_passwd=False):
        if cancel_func is None: cancel_func=self.cancel_func
        error=self.error()
        if error[0]:
            return 'error','''{}'''.format(error[1])
        while peeling:
            if type(cmd)is tuple and len(cmd) == 1:
                cmd=cmd[0]
            else:
                break
        if isinstance(cmd, (tuple,list)) and len(cmd) >= 2 and type(cmd[0]) is bool:
            ok,cmd,path,return_code,timeout_i=Get(cmd,[0,1,2,3,4],err=True,fill_up=None)
            if timeout_i: timeout=timeout_i
            if not ok:
                self.warn(_type='cmd',msg="command({}) format error".format(cmd))
                return False,(-1,'command format error(2)','command format error',0,0,cmd,path),'command({}) format error'.format(cmd)
        elif not isinstance(cmd,str):
            self.warn(_type='cmd',msg="command({}) format error".format(cmd))
            return False,(-1,'command format error(3)','command format error',0,0,cmd,path),'command({}) format error'.format(cmd)
        if not isinstance(return_code,dict):
            return_code={}
        rc_ok=return_code.get('ok',[0,True])
        rc_ignore=return_code.get('ignore',[])
        rc_fail=return_code.get('fail',[])
        rc_error=return_code.get('error',[127])
        rc_err_connection=return_code.get('err_connection',[])
        rc_err_key=return_code.get('err_key',[])
        rc_err_bmc_user=return_code.get('err_bmc_user',[])
        rc_err_bmc_redfish=return_code.get('err_bmc_redfish',[])
        rc_err_bmc_user_times=0
        if ip is None: ip=self.ip
        if user is None: user=self.user
        if passwd is None: passwd=self.passwd
        if type(append) is not str:
            append=''
        rc=None
        
        retry_passwd=2
        if isinstance(cmd,dict):
            if '{passwd}' not in cmd['base']:  retry_passwd=1
        else:
            if '{passwd}' not in cmd:  retry_passwd=1
        if not isinstance(retry,int) or isinstance(retry,bool): retry=0
        for x in range(0,1+retry):
            if x > 0:
                printf('Re-try command [{}/{}]'.format(x,retry),log=self.log,log_level=1,dsp='d',start_newline=True)
            for i in range(0,retry_passwd):
                if isinstance(cmd,dict):
                    base_cmd=sprintf(cmd['base'],**{'ip':ip,'user':user,'passwd':passwd})
                    cmd_str='''{} {} {}'''.format(base_cmd[1],cmd.get('cmd'),append)
                else:
                    base_cmd=sprintf(cmd,**{'ip':ip,'user':user,'passwd':passwd})
                    cmd_str='''{} {}'''.format(base_cmd[1],append)
                if not base_cmd[0]:
                    return False,(-1,'Wrong commnd format','Wrong command format',0,0,cmd_str,path),'Command format is wrong'
                if dbg or show_str:
                    if show_str: progress=True
                    if cd is True:
                         cmd_str_a=cmd_str.split()
                         if cmd_str_a[0][0] == '/':
                             cmd_str_a[0]=os.path.basename(cmd_str_a[0])
                             cmd_str=' '.join(cmd_str_a)
                    printf('''** Do CMD   : %s
 - Path         : %s
 - Timeout      : %-15s  - Progress : %s
 - Check_RC     : %s'''%(cmd_str,path,timeout,progress,return_code),log=self.log,log_level=1,dsp='d' if dbg else 's')
                if self.cancel(cancel_func=cancel_func):
                    printf(' !! Canceling Job',start_newline=True,log=self.log,log_level=1,dsp='d')
                    self.warn(_type='cancel',msg="Canceling")
                    return False,(-1,'canceling','canceling',0,0,cmd_str,path),'canceling'
                try:
                    rc=rshell(cmd_str,path=path,timeout=timeout,progress=progress,log=self.log,cd=cd,keep_cwd=keep_cwd)
                    if Get(rc,0) == -2 : return False,rc,'Timeout({})'.format(timeout)
                    if rc[0] !=0 and rc[0] in check_password_rc:
                        printf('Password issue, try again after check BMC user/password',start_newline=True,log=self.log,log_level=4,dsp='d')
                        ok,ip,user,passwd=self.check(mac2ip=self.mac2ip,cancel_func=cancel_func,trace=trace_passwd)
                        time.sleep(2)
                        continue
                except:
                    e = ExceptMessage()
                    printf('[ERR] Your command({}) got error\n{}'.format(cmd_str,e),start_newline=True,log=self.log,log_level=4,dsp='f')
                    self.warn(_type='cmd',msg="Your command({}) got error\n{}".format(cmd_str,e))
                    return 'error',(-1,'Your command({}) got error\n{}'.format(cmd_str,e),'unknown',0,0,cmd_str,path),'Your command got error'

                printf(' - CMD : {}\n - RT_CODE : {}\n - Output  : {}'.format(cmd_str,Get(rc,0),Get(rc,1)),log=self.log,log_level=1, mode='s' if show_str else 'i' if Get(rc,0) == 0 else 'd')

                rc_0=Get(rc,0)
                if 'Function access denied' in Get(rc,1):
                    return False,rc,'Locked BMC'
                elif rc_0 == 1:
                    return False,rc,'Command file not found'
                elif (not rc_ok and rc_0 == 0) or IsIn(rc_0,rc_ok):
                    return True,rc,'ok'
                elif IsIn(rc_0,rc_err_bmc_redfish): # retry after reset the BMC
                    if not self.McResetCold(self.ip):
                        return False,(-1,'Looks Stuck at BMC and Can not reset the BMC','Looks Stuck at BMC and Can not reset the BMC',0,0,cmd_str,path),'reset bmc'
                elif IsIn(rc_0,rc_err_connection): # retry condition1
                    msg='err_connection'
                    printf('Connection error condition:{}, return:{}'.format(rc_err_connection,Get(rc,0)),start_newline=True,log=self.log,log_level=7)
                    printf('Connection Error:',log=self.log,log_level=1,dsp='d',direct=True)
                    #Check connection
                    ping_start=datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")
                    ping_rc=ping(self.ip,keep_bad=1800,log=self.log,stop_func=self.error(_type='break')[0],cancel_func=self.cancel(cancel_func=cancel_func),keep_good=0,timeout=self.timeout)
                    ping_end=datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")
                    if ping_rc is 0:
                        printf(' !! Canceling Job',start_newline=True,log=self.log,log_level=1,dsp='d')
                        self.warn(_type='cancel',msg="Canceling")
                        return False,(-1,'canceling','canceling',0,0,cmd_str,path),'canceling'
                    elif ping_rc is False:
                        printf('Lost Network',start_newline=True,log=self.log,log_level=1,dsp='d')
                        self.error(_type='net',msg="{} lost network (over 30min)(1)({} - {})".format(self.ip,ping_start,ping_end))
                        return False,rc,'Lost Network, Please check your server network(1)'
                elif IsIn(rc_0,rc_err_bmc_user) and retry_passwd > 1 and i < 1: # retry condition1
                    printf('Issue in BMC Login issue({})'.format(rc_err_bmc_user),log=self.log,log_level=1,dsp='d')
                    #Check connection
                    ping_start=datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")
                    ping_rc=ping(self.ip,keep_bad=1800,log=self.log,stop_func=self.error(_type='break')[0],cancel_func=self.cancel(cancel_func=cancel_func),keep_good=0,timeout=self.timeout)
                    ping_end=datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")
                    if ping_rc is 0:
                        printf(' !! Canceling Job',start_newline=True,log=self.log,log_level=1,dsp='d')
                        self.warn(_type='cancel',msg="Canceling")
                        return False,(-1,'canceling','canceling',0,0,cmd_str,path),'canceling'
                    elif ping_rc is False:
                        printf('Lost Network',start_newline=True,log=self.log,log_level=1,dsp='d')
                        self.error(_type='net',msg="{} lost network (over 30min)(2)({}-{})".format(self.ip,ping_start,ping_end))
                        return False,rc,'Lost Network, Please check your server network(2)'
                    # Find Password
                    cur_user=self.__dict__.get('user')
                    cur_pass=self.__dict__.get('passwd')
                    ok,ipmi_user,ipmi_pass=self.find_user_pass()
                    if not ok:
                        self.error(_type='ipmi_user',msg="Can not find working IPMI USER and PASSWORD")
                        return False,'Can not find working IPMI USER and PASSWORD','user error'
                    printf('Check IPMI User and Password by {}: Found ({}/{})'.format(rc_err_bmc_user,ipmi_user,ipmi_pass),log=self.log,log_level=1,dsp='d')
                    if cur_user == ipmi_user and cur_pass == ipmi_pass:
                        printf('Looks Stuck at BMC, So reset the BMC and try again',start_newline=True,log=self.log,log_level=1,dsp='d')
                        if not self.McResetCold(self.ip):
                            return False,(-1,'Looks Stuck at BMC and Can not reset the BMC','Looks Stuck at BMC and Can not reset the BMC',0,0,cmd_str,path),'reset bmc'
                    user='{}'.format(ipmi_user)
                    passwd='''{}'''.format(ipmi_pass)
                else:
                    if 'ipmitool' in cmd_str and retry_passwd > 1 and i < 1:
                        printf('Issue of ipmitool command',log=self.log,log_level=1,dsp='d')
                        #Check connection
                        ping_start=datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")
                        ping_rc=ping(self.ip,keep_bad=1800,log=self.log,stop_func=self.error(_type='break')[0],cancel_func=self.cancel(cancel_func=cancel_func),keep_good=0,timeout=self.timeout)
                        ping_end=datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")
                        if ping_rc is 0:
                            printf(' !! Canceling Job',log=self.log,log_level=1,dsp='d')
                            self.warn(_type='cancel',msg="Canceling")
                            return False,(-1,'canceling','canceling',0,0,cmd_str,path),'canceling'
                        elif ping_rc is False:
                            printf('Lost Network',log=self.log,log_level=1,dsp='d')
                            self.error(_type='net',msg="{} lost network (over 30min)(3)({} - {})".format(self.ip,ping_start,ping_end))
                            return False,rc,'Lost Network, Please check your server network(3)'
                        # Find Password
                        ok,ipmi_user,ipmi_pass=self.find_user_pass()
                        if not ok:
                            self.error(_type='ipmi_user',msg="Can not find working IPMI USER and PASSWORD")
                            return False,'Can not find working IPMI USER and PASSWORD','user error'
                        printf('Check IPMI User and Password by ipmitool command: Found ({}/{})'.format(ipmi_user,ipmi_pass),log=self.log,log_level=1,dsp='d')
                        user='{}'.format(ipmi_user)
                        passwd='''{}'''.format(ipmi_pass)
                    else:
                        try:
                            if IsIn(rc_0,rc_ignore):
                                return 'ignore',rc,'return code({}) is in ignore condition({})'.format(rc[0],rc_ignore)
                            elif IsIn(rc_0,rc_fail):
                                return False,rc,'return code({}) is in fail condition({})'.format(rc[0],rc_fail)
                            elif IsIn(rc_0,[127]):
                                return False,rc,'no command'
                            elif IsIn(rc_0,rc_error):
                                return 'error',rc,'return code({}) is in error condition({})'.format(rc[0],rc_error)
                            elif IsIn(rc_0,rc_err_key):
                                return 'error',rc,'return code({}) is in key error condition({})'.format(rc[0],rc_err_key)
                            elif IsIn(rc_0,rc_err_bmc_user):
                                return 'error',rc,'return code({}) is in User/Password issue condition({})'.format(rc[0],rc_err_bmc_user)
                            elif isinstance(rc,tuple) and rc_0 > 0:
                                return False,rc,'Not defined return-condition, So it will be fail'
                        except:
                            return 'unknown',rc,'Unknown result'
        if rc is None:
            return False,(-1,'No more test','',0,0,cmd_str,path),'Out of testing'
        else:
            return False,rc,'Out of testing'

    def reset(self,retry=0,post_keep_up=20,pre_keep_up=0,retry_interval=5,cancel_func=None):
        for i in range(0,1+retry):
            for mm in self.cmd_module:
                ping_rc=ping(self.ip,timeout=1800,keep_good=pre_keep_up,log=self.log,stop_func=self.error(_type='break')[0],cancel_func=cancel_func)
                if ping_rc is 0:
                    return 0,'Canceled'
                elif ping_rc is False:
                    printf('R',log=self.log,log_level=1,direct=True)
                    rc=self.run_cmd(mm.cmd_str('ipmi reset'))
                    if krc(rc[0],chk='error'):
                        return rc
                    if krc(rc[0],chk=True):
                        ping_rc=ping(self.ip,timeout=1800,keep_good=post_keep_up,log=self.log,stop_func=self.error(_type='break')[0],cancel_func=cancel_func)
                        if ping_rc is 0:
                            return 0,'Canceled'
                        elif ping_rc is True:
                            return True,'Pinging to BMC after reset BMC'
                        else:
                            return False,'Can not Pinging to BMC after reset BMC'
                elif i >= retry:
                    return False,'Can not Pinging to BMC. I am not reset the BMC. please check the network first!'
                time.sleep(retry_interval)
        return False,'Something issue'

    def get_mac(self,ip=None,user=None,passwd=None):
        if self.mac:
            return True,self.mac
        if ip is None: ip=self.ip
        ok,user,passwd=self.find_user_pass()
        if not ok: return False,None
        for mm in self.cmd_module:
            name=mm.__name__
            cmd_str=mm.cmd_str('ipmi lan mac',passwd=self.passwd)
            full_str=cmd_str[1]['base'].format(ip=ip,user=user,passwd=passwd)+' '+cmd_str[1]['cmd']
            rc=rshell(full_str,log=self.log)
            if krc(rc[0],chk=True):
                if name == 'smc':
                    self.mac=rc[1].lower()
                    return True,self.mac
                elif name == 'ipmitool':
                    for ii in rc[1].split('\n'):
                        ii_a=ii.split()
                        if IsIn('MAC',ii_a,idx=0) and IsIn('Address',ii_a,idx=1) and IsIn(':',ii_a,idx=2):
                            self.mac=ii_a[-1].lower()
                            return True,self.mac
        return False,None

    def dhcp(self):
        for mm in self.cmd_module:
            name=mm.__name__
            rc=self.run_cmd(mm.cmd_str('ipmi lan dhcp',passwd=self.passwd))
            if krc(rc[0],chk='error'):
                return rc
            if krc(rc[0],chk=True):
                if name == 'smc':
                    return True,rc[1]
                elif name == 'ipmitool':
                    for ii in rc[1][1].split('\n'):
                        ii_a=ii.split()
                        if IsIn('IP',ii_a,idx=0) and IsIn('Address',ii_a,idx=1) and IsIn('Source',ii_a,idx=2):
                            return True,ii_a[-2]
        return False,None

    def gateway(self):
        for mm in self.cmd_module:
            name=mm.__name__
            rc=self.run_cmd(mm.cmd_str('ipmi lan gateway',passwd=self.passwd))
            if krc(rc[0],chk='error'):
                return rc
            if krc(rc[0],chk=True):
                if name == 'smc':
                    return True,rc[1]
                elif name == 'ipmitool':
                    for ii in rc[1][1].split('\n'):
                        ii_a=ii.split()
                        if IsIn('Default',ii_a,idx=0) and IsIn('Gateway',ii_a,idx=1) and IsIn('IP',ii_a,idx=2):
                            return True,ii_a[-1]
        return False,None

    def netmask(self):
        for mm in self.cmd_module:
            name=mm.__name__
            rc=self.run_cmd(mm.cmd_str('ipmi lan netmask',passwd=self.passwd))
            if krc(rc[0],chk='error'):
                return rc
            if krc(rc[0],chk=True):
                if name == 'smc':
                    return True,rc[1]
                elif name == 'ipmitool':
                    for ii in rc[1][1].split('\n'):
                        ii_a=ii.split()
                        if IsIn('Subnet',ii_a,idx=0) and IsIn('Mask',ii_a,idx=1):
                            return True,ii_a[-1]
        return krc(rc[0]),None

    def SetPXE(self,ipxe=True,persistent=True,set_bios_uefi=False,force=False):
        # 0. Check boot order and not set then keep going
        # 1. turn off system
        # 2. Set Boot Order
        # 3. turn on system
        # 4. Check correctly setup or not
        # 5. Return
        if not force:
            crc=self.bootorder(mode='status')
            printf('Current Boot order is {}{}'.format(crc[0],' with UEFI mode' if crc[1] else ''),log=self.log,log_level=6)
            if crc[0] == 'pxe':
                if ipxe:
                    if crc[1]:
                        printf('Already it has PXE Config with UEFI mode',log=self.log,log_level=6)
                        return True,'Already it has PXE Config with UEFI mode',crc[2]
                else:
                    if not crc[1]:
                        printf('Already it has PXE Config',log=self.log,log_level=6)
                        return True,'Already it has PXE Config',crc[2]
                printf('Wrong Configuration({}PXE)'.format('i' if crc[1] else ''),log=self.log,log_level=3)
        if self.power('off',verify=True):
            if self.is_down(timeout=1200,interval=5,sensor_off_monitor=5,keep_off=5):
                br_rc=self.bootorder(mode='pxe',ipxe=ipxe,force=True,persistent=persistent,set_bios_uefi=set_bios_uefi)
                if br_rc[0]:
                    if self.power('on',verify=False):
                        time.sleep(10)
                        frc_msg=''
                        for i in range(0,200):
                            frc=self.bootorder(mode='status')
                            if frc[0] == 'pxe':
                                if ipxe:
                                    if frc[1]: 
                                        printf('Set to PXE Config with UEFI mode',log=self.log,log_level=6)
                                        return True,'Set to PXE Config with UEFI mode',frc[2]
                                else:
                                    if not frc[1]:
                                        printf('Set to PXE Config',log=self.log,log_level=6)
                                        return True,'Set to PXE Config',frc[2]
                            printf('.',direct=True,log=self.log,log_level=1)
                            frc_msg='got {} Config{}'.format(frc[0],' with UEFI mode' if crc[1] else '')
                            time.sleep(6)
                        printf('Can not find {}PXE Config, Currently it {}'.format('i' if ipxe else '',frc_msg),log=self.log,log_level=6)
                        return False,'Can not find {}PXE Config, Currently it {}'.format('i' if ipxe else '',frc_msg),False
                    else:
                        printf('Can not power on the server',log=self.log,log_level=6)
                        return False,'Can not power on the server',False
                else:
                    printf(br_rc[1],log=self.log,log_level=6)
                    return False,br_rc[1],False
            else:
                printf('The server still UP over 20min',log=self.log,log_level=6)
                return False,'The server still UP over 20min',False
        else:
            printf('Can not power off the server',log=self.log,log_level=6)
            return False,'Can not power off the server',False

    def bootorder(self,mode=None,ipxe=False,persistent=False,force=False,boot_mode={'smc':['pxe','bios','hdd','cd','usb'],'ipmitool':['pxe','ipxe','bios','hdd']},bios_cfg=None,set_bios_uefi=True):
        rc=False,"Unknown boot mode({})".format(mode)
        ipmi_ip=self.ip

        def ipmitool_bootorder_setup(mm,mode,persistent,ipxe):
            #######################
            # Setup Boot order
            #######################
            rf=self.CallRedfish()
            if rf:
                # Update new information
                ok,rf_boot=rf.Boot(boot='ipxe' if (ipxe and mode == 'pxe') or (mode == 'ipxe') else mode,mode='UEFI' if mode == 'ipxe' or (mode == 'pxe' and ipxe is True) else 'auto',keep='keep' if persistent else 'Once',force=force,set_bios_uefi=set_bios_uefi)
                printf("[RF] {2} Boot mode set to {0} at {1}".format('ipxe' if (ipxe and mode == 'pxe') or (mode == 'ipxe') else mode,ipmi_ip,'Persistently' if persistent else 'Temporarily'),log=self.log,log_level=7)
                rc=ok,(ok,'Persistently set to {}'.format('ipxe' if (ipxe and mode == 'pxe') or (mode == 'ipxe') else mode) if ok else rf_boot)
            else:
                if mode == 'pxe' and IsIn(ipxe,['on',True,'True']):
                    # ipmitool -I lanplus -H 172.16.105.74 -U ADMIN -P 'ADMIN' raw 0x00 0x08 0x05 0xe0 0x04 0x00 0x00 0x00
                    if persistent:
                        ipmi_cmd='raw 0x00 0x08 0x05 0xe0 0x04 0x00 0x00 0x00'
                    else:
                        ipmi_cmd='chassis bootdev {0} options=efiboot'.format(mode)
                    rc=self.run_cmd(mm.cmd_str(ipmi_cmd,passwd=self.passwd))
                    printf("{1} Boot mode set to iPXE at {0}".format(ipmi_ip,'Persistently' if persistent else 'Temporarily'),log=self.log,log_level=7)
                else:
                    rc=self.run_cmd(mm.cmd_str('chassis bootdev {0}{1}'.format(mode,' options=persistent' if persistent else ''),passwd=self.passwd))
                    printf("{2} Boot mode set to {0} at {1}".format(mode,ipmi_ip,'Persistently' if persistent else 'Temporarily'),log=self.log,log_level=7)

            if krc(rc[0],chk=True):
                return True,rc[1][1]
            return rc

        def smcipmitool_bootorder_setup(mm,mode,persistent,ipxe):
            #SMCIPMITool command : Setup
            if mode == 'pxe':
                rc=self.run_cmd(mm.cmd_str('ipmi power bootoption 1',passwd=self.passwd))
            elif mode == 'hdd':
                rc=self.run_cmd(mm.cmd_str('ipmi power bootoption 2',passwd=self.passwd))
            elif mode == 'cd':
                rc=self.run_cmd(mm.cmd_str('ipmi power bootoption 3',passwd=self.passwd))
            elif mode == 'bios':
                rc=self.run_cmd(mm.cmd_str('ipmi power bootoption 4',passwd=self.passwd))
            elif mode == 'usb':
                rc=self.run_cmd(mm.cmd_str('ipmi power bootoption 6',passwd=self.passwd))
            if krc(rc[0],chk=True):
                return True,rc[1][1]
            return rc

        def ipmitool_bootorder_status(mm,mode,bios_cfg):
            #IPMITOOL command
            if IsIn(mode,['order',None]): # Show Boot Order
                #If exist redfish then try redfish first
                rf=self.CallRedfish()
                if rf:
                    return rf.Boot(boot='order')
                rc=self.run_cmd(mm.cmd_str('chassis bootparam get 5',passwd=self.passwd))
                # Boot Flags :
                #   - Boot Flag Invalid
                #   - Options apply to only next boot
                #   - BIOS EFI boot 
                #   - Boot Device Selector : Force PXE
                #   - Console Redirection control : System Default
                #   - BIOS verbosity : Console redirection occurs per BIOS configuration setting (default)
                #   - BIOS Mux Control Override : BIOS uses recommended setting of the mux at the end of POST
                if rc[0]:
                    found=FIND(rc[1]).Find('- Boot Device Selector : (\w.*)')
                    if found:
                        return True,found[0]
                    return True,None
            # Status : output: [status, uefi, persistent]
            elif mode in ['status','detail']:
                status=False
                efi=False
                persistent=False
                #If redfish
                rf=self.CallRedfish()
                if rf:
                    ok,rf_boot_info=rf.Boot()
                    #Detail information : output : dictionary
                    if mode == 'detail':
                        return rf_boot_info

                    #Simple information : [status, uefi, persistent]
                    if rf_boot_info.get('order',{}).get('enable','') == 'Disabled': #Follow BIOS setting
                        if rf_boot_info.get('bios',{}).get('mode','') == 'Dual':
                            if 'UEFI PXE' in Get(rf_boot_info.get('bios',{}).get('order',[]),0,default=''):
                                status='pxe'
                                efi=True
                                persistent=True
                            elif 'Network:IBA' in Get(rf_boot_info.get('bios',{}).get('order',[]),0,default=''):
                                status='pxe'
                                efi=False
                                persistent=True
                        else:
                            efi=True if rf_boot_info.get('bios',{}).get('mode','') == 'UEFI' else False
                            if 'Network:' in Get(rf_boot_info.get('bios',{}).get('order',[]),0,default=''):
                                status='pxe'
                                persistent=True
                    else: # Follow instant overwriten Boot-Order
                        efi=True if rf_boot_info.get('order',{}).get('mode','') == 'UEFI' else False
                        status=rf_boot_info.get('order',{}).get('1','').lower()
                        persistent=True if rf_boot_info.get('order',{}).get('enable','') == 'Continuous' else False
                    return [status,efi,persistent]
                #If received bios_cfg file
                if bios_cfg:
                    bios_cfg=self.find_uefi_legacy(bioscfg=bios_cfg)
                    if krc(rc,chk=True): # ipmitool bootorder
                        status='No override'
                        for ii in Get(rc[1],1).split('\n'):
                            if 'Options apply to all future boots' in ii:
                                persistent=True
                            elif 'BIOS EFI boot' in ii:
                                efi=True
                            elif 'Boot Device Selector :' in ii:
                                status=ii.split(':')[1]
                                break
                        printf("Boot mode Status:{}, EFI:{}, Persistent:{}".format(status,efi,persistent),log=self.log,log_level=7)
                    if krc(bios_cfg,chk=True): #BIOS CFG file
                        bios_uefi=Get(bios_cfg,1)
                        if 'EFI' in bios_uefi[0:-1] or 'UEFI' in bios_uefi[0:-1] or 'IPXE' in bios_uefi[0:-1]:
                            efi=True
                #If not special, so get information from ipmitool
                else:
                    rc=self.run_cmd(mm.cmd_str('chassis bootparam get 5',passwd=self.passwd))
                    if mode == 'detail':
                        return rc
                    if rc[0]:
                        efi_found=FIND(rc[1]).Find('- BIOS (\w.*) boot')
                        if efi_found:
                            if isinstance(efi_found,list):
                                if 'EFI' in efi_found[0]:
                                    efi=True
                                    status='pxe'
                            elif isinstance(efi_found,str):
                                if 'EFI' in efi_found:
                                    efi=True
                                    status='pxe'
                        found=FIND(rc[1]).Find('- Boot Device Selector : (\w.*)')
                        if found:
                            if isinstance(found,list):
                                if 'Force' in found[0]:
                                    persistent=True
                                if 'PXE' in found[0]:
                                    status='pxe'
                            elif isinstance(found,str):
                                if 'Force' in found:
                                    persistent=True
                                if 'PXE' in found:
                                    status='pxe'
                return [status,efi,persistent]

        for mm in self.cmd_module:
            name=mm.__name__
            chk_boot_mode=boot_mode.get(name,{})
            if name == 'smc' and mode in chk_boot_mode:
                # Setup Boot order by SMCIPMITool
                return smcipmitool_bootorder_setup(mm,mode,persistent,ipxe)
            elif name == 'ipmitool':
                # return Status
                if IsIn(mode,[None,'order','status','detail']):
                    return ipmitool_bootorder_status(mm,mode,bios_cfg)
                # If unknown mode then error
                elif mode not in chk_boot_mode:
                    self.warn(_type='boot',msg="Unknown boot mode({}) at {}".format(mode,name))
                    return False,'Unknown boot mode({}) at {}'.format(mode,name)
                else:
                    # Setup Boot order
                    return ipmitool_bootorder_setup(mm,mode,persistent,ipxe)
            else:
                return False,'Unknown module name'
        return False,rc[-1]

    def get_eth_mac(self,port=None):
        if self.eth_mac:
            return True,self.eth_mac
        rc=False,[]
        for mm in self.cmd_module:
            name=mm.__name__
            if name == 'ipmitool':
                aaa=mm.cmd_str('''raw 0x30 0x21''',passwd=self.passwd)
                rc=self.run_cmd(aaa)
                if krc(rc[0],chk=True) and rc[1][1]:
                    mac_source=rc[1][1].split('\n')[0].strip()
                    if mac_source:
                        if len(mac_source.split()) == 10:  
                            eth_mac=':'.join(mac_source.split()[-6:]).lower()
                        elif len(mac_source.split()) == 16:
                            eth_mac=':'.join(mac_source.split()[-12:-6]).lower()
                        if not MacV4(eth_mac) or eth_mac == '00:00:00:00:00:00':
                            rf=self.CallRedfish()
                            mac=rf.PXEMAC()
                            if MacV4(mac) and mac!= '00:00:00:00:00:00':
                                eth_mac=mac
                        if MacV4(eth_mac) and eth_mac != '00:00:00:00:00:00':
                            self.eth_mac=eth_mac
                            return True,self.eth_mac
            elif name == 'smc':
                rc=self.run_cmd(mm.cmd_str('ipmi oem summary | grep "System LAN"',passwd=self.passwd))
                if krc(rc[0],chk=True):
                    #rrc=[]
                    #for ii in rc[1].split('\n'):
                    #    rrc.append(ii.split()[-1].lower())
                    #self.eth_mac=rrc
                    eth_mac=rc[1].split('\n')[0].strip().lower()
                    if MacV4(eth_mac) and eth_mac != '00:00:00:00:00:00':
                        self.eth_mac=eth_mac
                        return True,self.eth_mac
            #if krc(rc[0],chk='error'):
            #   return rc
        #If not found then try with redfish
        rf=self.CallRedfish()
        if rf:
            rf_base=rf.BaseMac()
            if rf_base.get('lan') and rf_base.get('lan') == rf_base.get('bmc'):
                rf_net=rf.Network()
                for nid in rf_net:
                    for pp in rf_net[nid].get('port',{}):
                        port_state=rf_net[nid]['port'][pp].get('state')
                        if port:
                            if '{}'.format(port) == '{}'.format(pp):
                                if MacV4(rf_net[nid]['port'][pp].get('mac')):
                                    self.eth_mac=rf_net[nid]['port'][pp].get('mac')
                                    return True,self.eth_mac
                        elif isinstance(port_state,str) and port_state.lower() == 'up':
                            if MacV4(rf_net[nid]['port'][pp].get('mac')):
                                self.eth_mac=rf_net[nid]['port'][pp].get('mac')
                                return True,self.eth_mac
            else:
                if MacV4(rf_base.get('lan')):
                    return True,rf_base.get('lan')
        return False,None

    def get_eth_info(self):
        ok,ip,user,passwd=self.check(mac2ip=self.mac2ip)
        rf=Redfish(host=ip,user=user,passwd=passwd,log=self.log)
        return rf.Network()

    def summary(self): # BMC is ready(hardware is ready)
        if ping(self.ip,timeout=self.timeout,bad=30) is False:
            print('%10s : %s'%("Ping","Fail"))
            return False
        print('%10s : %s'%("Ping","OK"))
        self.check(mac2ip=self.mac2ip,cancel_func=self.cancel_func)
        print('%10s : %s'%("User",self.user))
        print('%10s : %s'%("Password",self.passwd))
        ok,mac=self.get_mac()
        print('%10s : %s'%("Bmc Mac",'{}'.format(mac)))
        ok,eth_mac=self.get_eth_mac()
        if ok:
            print('%10s : %s'%("Eth Mac",'{}'.format(eth_mac)))
        print('%10s : %s'%("Power",'{}'.format(self.power('status'))))
        print('%10s : %s'%("DHCP",'{}'.format(self.dhcp()[1])))
        print('%10s : %s'%("Gateway",'{}'.format(self.gateway()[1])))
        print('%10s : %s'%("Netmask",'{}'.format(self.netmask()[1])))
        print('%10s : %s'%("LanMode",'{}'.format(self.lanmode()[1])))
        print('%10s : %s'%("BootOrder",'{}'.format(self.bootorder()[1])))


    def is_up(self,timeout=1200,interval=8,sensor_on_monitor=600,reset_after_unknown=0,status_log=True,**opts):
        keep_on=Pop(opts,'keep_up',Pop(opts,'keep_on',30))
        keep_off=Pop(opts,'keep_down',Pop(opts,'keep_off',0))
        opts['mode']=opts.get('mode','s')
        rt=self.power_monitor(Int(timeout,default=1200),monitor_status=['on'],keep_off=keep_off,keep_on=keep_on,sensor_on_monitor=sensor_on_monitor,sensor_off_monitor=0,monitor_interval=interval,start=True,background=False,status_log=status_log,reset_after_unknown=reset_after_unknown,**opts)
        out=next(iter(rt.get('done').values())) if isinstance(rt.get('done'),dict) else rt.get('done')
        if isinstance(rt.get('monitored_order'),list):
            if rt.get('monitored_order')[-1] == 'on':
                if rt.get('repeat',0) > 0:
                    return True,'{} but repeated down and up to {}'.format(out,rt.get('repeat',0))
                return True,next(iter(out.values())) if isinstance(out,dict) else out
        return False,out

    def is_down_up(self,timeout=1200,sensor_on_monitor=600,sensor_off_monitor=0,interval=8,status_log=True,reset_after_unknown=0,**opts): # Node state
        keep_on=Pop(opts,'keep_up',Pop(opts,'keep_on',60))
        keep_off=Pop(opts,'keep_down',Pop(opts,'keep_off',0))
        opts['mode']=opts.get('mode','s')
        rt=self.power_monitor(Int(timeout,default=1200),monitor_status=['off','on'],keep_off=keep_off,keep_on=keep_on,sensor_on_monitor=sensor_on_monitor,sensor_off_monitor=sensor_off_monitor,monitor_interval=interval,start=True,background=False,status_log=status_log,reset_after_unknown=reset_after_unknown,**opts)
        out=next(iter(rt.get('done').values())) if isinstance(rt.get('done'),dict) else rt.get('done')
        if isinstance(rt.get('monitored_order'),list):
            if rt.get('monitored_order')[-1] == 'on' and 'off' in rt.get('monitored_order'):
                if rt.get('repeat',0) > 0:
                    return True,'{} but repeated down and up to {}'.format(out,rt.get('repeat',0))
                return True,out
        return False,out

    def is_down(self,timeout=1200,interval=8,sensor_off_monitor=0,status_log=True,reset_after_unknown=0,**opts): # Node state
        keep_on=Pop(opts,'keep_up',Pop(opts,'keep_on',0))
        keep_off=Pop(opts,'keep_down',Pop(opts,'keep_off',20))
        opts['mode']=opts.get('mode','s')
        rt=self.power_monitor(Int(timeout,default=1200),monitor_status=['off'],keep_off=keep_off,keep_on=keep_on,sensor_on_monitor=0,sensor_off_monitor=sensor_off_monitor,monitor_interval=interval,start=True,background=False,status_log=status_log,reset_after_unknown=reset_after_unknown,**opts)
        out=next(iter(rt.get('done').values())) if isinstance(rt.get('done'),dict) else rt.get('done')
        if isinstance(rt.get('monitored_order'),list):
            if rt.get('monitored_order')[-1] == 'off':
                if rt.get('repeat',0) > 0:
                    return True,'{} but repeated up and down to {}'.format(out,rt.get('repeat',0))
                return True,out
        return False,out

    def get_boot_mode(self):
        return self.bootorder(mode='status')

    def power(self,cmd='status',retry=0,boot_mode=None,order=False,ipxe=False,log_file=None,log=None,force=False,mode=None,verify=True,post_keep_up=20,pre_keep_up=0,post_keep_down=0,timeout=1800,lanmode=None,fail_down_time=240,cancel_func=None,set_bios_uefi_mode=False,monitor_mode='a'):
        # verify=False
        #  - just send a command 
        #  - if off_on command then check off mode without sensor monitor
        #    and on case, just send a on command
        # post_keep_up, post_keep_down,pre_keep_up : required verify=True
        # monitor_mode : when verify is True then required this.
        retry=Int(retry,default=0)
        timeout=Int(timeout,default=1800)
        pre_keep_up=Int(pre_keep_up,default=0)
        post_keep_up=Int(post_keep_up,default=20)
        post_keep_down=Int(post_keep_down,default=0)
        if cancel_func is None: cancel_func=self.cancel_func
        if cmd == 'status':
            aa=self.do_power('status',verify=verify)
            if aa[0]:
                return aa[1]
            elif self.redfish:
                rf=self.CallRedfish()
                if rf:
                    rfp=rf.Power('status')
                    if IsIn(rfp,['on','off']): return rfp
            return aa[1]
        if boot_mode:
            if boot_mode == 'ipxe' or ipxe:
                ipxe=True
                boot_mode='pxe'
            for ii in range(0,retry+1):
                # Find ipmi information
                printf('Set {}{}{} boot mode ({}/{})'.format('force ' if force else '','i' if ipxe else '',boot_mode,ii+1,retry),log=self.log,log_level=3)
                ok,ip,user,passwd=self.check(mac2ip=self.mac2ip,cancel_func=cancel_func)
                #Check Status
                boot_mode_state=self.bootorder(mode='status')
                if IsSame(boot_mode,boot_mode_state[0]) and IsSame(ipxe,boot_mode_state[1]):
                    if boot_mode_state[2] is True or IsSame(order,boot_mode_state[2]):
                        break
                rc=self.bootorder(mode=boot_mode,ipxe=ipxe,persistent=True,force=True)
                if rc[0]:
                    printf('Set Done: {}'.format(rc[1]),log=self.log,log_level=3)
                    time.sleep(30)
                    break
                if 'Not licensed to perform' in rc[1]:
                    printf('Product KEY ISSUE. Set ProdKey and try again.....',log=self.log,log_level=3)
                    return False,rc[1],-1
                time.sleep(10)
        return self.do_power(cmd,retry=retry,verify=verify,timeout=timeout,post_keep_up=post_keep_up,post_keep_down=post_keep_down,lanmode=lanmode,fail_down_time=fail_down_time,mode=monitor_mode)

    def do_power(self,cmd,retry=0,verify=False,timeout=1200,post_keep_up=40,post_keep_down=0,pre_keep_up=0,lanmode=None,cancel_func=None,fail_down_time=300,mode='a'):
        timeout=Int(timeout,default=1200)
        def lanmode_check(mode):
            # BMC Lan mode Checkup
            cur_lan_mode=self.lanmode()
            if cur_lan_mode[0]:
                if self.lanmode_convert(mode) == self.lanmode_convert(cur_lan_mode[1]):
                    printf(' Already {}'.format(self.lanmode_convert(mode,string=True)),log=self.log,log_level=7)
                    return self.lanmode_convert(cur_lan_mode[1],string=True)
                else:
                    rc=self.lanmode(mode)
                    if rc[0]:
                        printf(' Set to {}'.format(Get(rc,1)),log=self.log,log_level=5)
                        return Get(rc,1)
                    else:
                        printf(' Can not set to {}'.format(self.lanmode_convert(mode,string=True)),log=self.log,log_level=1)
        chkd=False
        for mm in self.cmd_module:
            name=mm.__name__
            if cmd not in ['status','off_on'] + list(mm.power_mode):
                printf('Unknown command({})'.format(cmd),no_intro=True,log=self.log,log_level=1)
                self.warn(_type='power',msg="Unknown command({})".format(cmd))
                return False,'Unknown command({})'.format(cmd),-1

            power_step=len(mm.power_mode[cmd])-1
            for ii in range(1,int(retry)+2):
                checked_lanmode=None
                if verify or cmd == 'status':
                    init_rc=self.run_cmd(mm.cmd_str('ipmi power status',passwd=self.passwd))
                    if krc(init_rc[0],chk='error'):
                        printf('Power status got some error ({})'.format(init_rc[-1]),log=self.log,log_level=3)
                        return init_rc[0],init_rc[1],ii
                    if init_rc[0] is False:
                        if init_rc[-1] == 'canceling':
                            printf(' Canceling',no_intro=True,log=self.log,log_level=1)
                            return True,'canceling',ii
                        else:
                            printf('Power status got some error ({})'.format(init_rc[-1]),slog=self.log,log_level=3)
                            self.warn(_type='power',msg="Power status got some error ({})".format(init_rc[-1]))
                            time.sleep(3)
                            continue
                    if cmd == 'status':
                        if init_rc[0]:
                            if cmd == 'status':
                                # No need new line
                                return True,init_rc[1][1],ii
                        time.sleep(3)
                        continue
                    init_status=Get(Get(Get(init_rc,1,default=[]),1,default='').split(),-1)
                    if init_status == 'off' and cmd in ['reset','cycle']:
                        cmd='on'
                    # keep command
                    if pre_keep_up > 0 and self.is_up(timeout=timeout,keep_up=pre_keep_up,cancel_func=cancel_func,keep_down=fail_down_time,mode=mode)[0] is False:
                        time.sleep(3)
                        continue
                printf('Power {} at {} (try:{}/{}) (limit:{} sec)'.format(cmd,self.ip,ii,retry+1,timeout),log=self.log,log_level=3)
                chk=1
                do_power_mode=mm.power_mode[cmd]
                verify_num=len(do_power_mode)
                for rr in range(0,verify_num):
                    verify_status=do_power_mode[rr].split(' ')[-1]
                    if verify:
                        if chk == 1 and init_rc[0] and init_status == verify_status:
                            if chk == verify_num:
                                #printf(self.power_on_tag if verify_status == 'on' else self.power_off_tag ,no_intro=True,log=self.log,log_level=1)
                                printf('* Already turned {}'.format(verify_status),no_intro=True,log=self.log,log_level=1)
                                return True,verify_status,ii
                            chk+=1
                            continue
                        # BMC Lan mode Checkup before power on/cycle/reset
                        if checked_lanmode is None and self.lanmode_convert(lanmode) in [0,1,2] and verify_status in ['on','reset','cycle']:
                           lanmode_check(lanmode)

                        if verify_status in ['reset','cycle']:
                             if init_status == 'off':
                                 printf(' ! can not {} the power'.format(verify_status),start_newline=True,log=self.log,log_level=1)
                                 self.warn(_type='power',msg="Can not set {} on the off mode".format(verify_status))
                                 return False,'can not {} the power'.format(verify_status)
                    printf('* Turn power {} '.format(verify_status),no_start_newline=True,end_newline=False,log=self.log,log_level=3,scr_dbg=False)
                    rc=self.run_cmd(mm.cmd_str(do_power_mode[rr],passwd=self.passwd),retry=retry)
                    if krc(rc,chk='error'):
                        printf(' ! power {} error\n{}'.format(verify_status,rc[1][2]),log=self.log,log_level=3)
                        return rc
                    if krc(rc,chk=True):
                        if verify_status in ['reset','cycle']:
                            verify_status='on'
                            if verify:
                                time.sleep(10)
                    else:
                        printf(' ! power {} fail\n{}'.format(verify_status,rc[1][2]),log=self.log,log_level=3)
                        self.warn(_type='power',msg="power {} fail".format(verify_status))
                        time.sleep(5)
                        break
                    if verify:
                        if verify_status in ['on','up']:
                            cc=TIME().Int()
                            is_up=self.is_up(timeout=timeout,keep_up=post_keep_up,cancel_func=cancel_func,keep_down=fail_down_time,mode=mode)
                            if is_up[0]:
                                if chk == len(mm.power_mode[cmd]):
                                    printf(self.power_on_tag,no_intro=True,log=self.log,log_level=1)
                                    return True,'on',ii
                                elif chk < len(mm.power_mode[cmd]):
                                    # It need new line for the next command
                                    printf(self.power_on_tag,no_intro=True,log=self.log,log_level=1)
                            elif is_up[1].split()[0] == 'down' and not chkd:
                                chkd=True
                                self.warn(_type='power',msg="Something weird. Looks BMC issue")
                                printf('[Something weird. Try again]',direct=True,log=self.log,log_level=1)
                                retry=retry+1 
                                time.sleep(20)
                                continue
                        elif verify_status in ['off','down']:
                            cc=TIME().Int()
                            is_down=self.is_down(cancel_func=cancel_func,keep_down=post_keep_down,mode=mode)
                            if is_down[0]:
                                if chk == len(mm.power_mode[cmd]):
                                    printf(self.power_off_tag,no_intro=True,log=self.log,log_level=1)
                                    return True,'off',ii
                                elif chk < len(mm.power_mode[cmd]):
                                    # It need new line for the next command
                                    printf(self.power_off_tag,no_intro=True,log=self.log,log_level=1)
                            elif is_down[1].split()[0] == 'up' and not chkd:
                                chkd=True
                                self.warn(_type='power',msg="Something weird. Looks BMC issue")
                                printf('[Something weird. Try again]',direct=True,log=self.log,log_level=1)
                                retry=retry+1 
                                time.sleep(20)
                                continue
                        chk+=1
                    else:
                        if cmd == 'off_on':
                            if verify_status in ['off','down']:
                                for i in range(0,30):
                                    init_rc=self.run_cmd(mm.cmd_str('ipmi power status',passwd=self.passwd))
                                    if krc(init_rc,chk=True):
                                        if init_rc[1][1].split()[-1] == 'off':
                                            printf( self.power_off_tag ,no_intro=True,log=self.log,log_level=1)
                                            chkd=True
                                            chk+=1
                                            break
                                    printf(self.power_on_tag if init_rc[1][1].split()[-1] == 'on' else self.power_off_tag ,direct=True,log=self.log,log_level=1)
                                    time.sleep(2)
                                continue
                        printf(self.power_on_tag if verify_status== 'on' else self.power_off_tag ,no_intro=True,log=self.log,log_level=1)
                        return True,Get(Get(rc,1),1),ii
                time.sleep(3)
        if chkd:
            printf(' It looks BMC issue. (Need reset the physical power)',log=self.log,log_level=1)
            self.error(_type='power',msg="It looks BMC issue. (Need reset the physical power)")
            return False,'It looks BMC issue. (Need reset the physical power)',ii
        return False,'time out',ii

    def lanmode_convert(self,mode=None,string=False):
        if isinstance(mode,str):
            if mode.lower() in ['dedicate','dedicated','0']:
                mode=0
            elif mode.lower() in ['share','shared','onboard','1']:
                mode=1
            elif mode.lower() in ['failover','ha','2']:
                mode=2
        if string:
            if mode == 0:
                return 'Dedicated'
            elif mode == 1:
                return 'Shared'
            elif mode == 2:
                return 'Failover'
            else:
                return 'Unknown'
        else:
            return mode

    def lanmode(self,mode=None):
        mm,msg=self.get_cmd_module_name('smc')
        if not mm:
            return False,msg
        if self.lanmode_convert(mode) in [0,1,2]:
            rc=self.run_cmd(mm.cmd_str("""ipmi oem lani {}""".format(self.lanmode_convert(mode)),passwd=self.passwd),timeout=5)
            if krc(rc[0],chk=True):
                return True,self.lanmode_convert(mode,string=True)
            return rc
        else:
            rc=self.run_cmd(mm.cmd_str("""ipmi oem lani""",passwd=self.passwd))
            if krc(rc[0],chk=True):
                if mode in ['info','support']:
                    return True,Get(Get(rc,1),1)
                else:
                    a=FIND(rc[1][1]).Find('Current LAN interface is \[ (\w.*) \]')
                    if len(a) == 1:
                        return True,a[0]
            return False,None

    def error(self,_type=None,msg=None):
        if _type and msg:
            self.err.update({_type:{TIME().Int():msg}})
        else:
            if not _type:
                if self.err: return True,self.err
                return False,'OK'
            else:
                get_msg=self.err.get(_type,None)
                if get_msg: return True,get_msg
                return False,None

    def warn(self,_type=None,msg=None):
        if _type and msg:
            self.warning.update({_type:{TIME().Int():msg}})
        else:
            if not _type:
                if self.warning: return True,self.warning
                return False,None
            else:
                get_msg=self.warning.get(_type,None)
                if get_msg: return True,get_msg
                return False,None

    def cancel(self,cancel_func=None,msg=None,log=None,log_level=1,parent=2,task_all_stop=True):
        #task_all_stop : True, stop kBMc all, False, Only check current step for cancel() 
        if cancel_func is None: cancel_func=self.cancel_func
        if log is None: log=self.log
        if self.canceling:
            return self.canceling
        else:
            if IsBreak(cancel_func,log=log,log_level=log_level):
                caller_name=FunctionName(parent=parent)
                caller_name='{}() : '.format(caller_name) if isinstance(caller_name,str) else ''
                if msg :
                    msg='{}{}'.format(caller_name,msg)
                else:
                    msg='{}Got Cancel Signal'.format(caller_name)
                printf(msg,log=log,log_level=log_level)
                if task_all_stop:
                    self.canceling.update({TIME().Int():msg})
                return True
        return False

    def is_admin_user(self,**opts):
        admin_id=opts.get('admin_id',2)
        defined_user=self.__dict__.get('user')
        found=None
        for mm in self.cmd_module:
            #name=mm.__name__
            for j in range(0,2):
                rc=self.run_cmd(mm.cmd_str("""user list"""))
                if krc(rc,chk=True):
                    for i in Get(Get(rc,1),1).split('\n'):
                        i_a=i.strip().split()
                        if str(admin_id) in i_a:
                            if Get(i_a,-1) == 'ADMINISTRATOR':
                                found=Get(i_a,1)
                                if defined_user == Get(i_a,1):
                                    return True,found
                else:
                    ok,user,passwd=self.find_user_pass()
                    if not ok: break
        return False,found
        
    def screen(self,cmd='info',title=None,find=[],timeout=600,session_out=180,stdout=False):
        #Screen Session default time out: 3min
        #monitor default time out: 10min
        pid=os.getpid()
        screen_tmp_file='/tmp/.screen.{}_{}.cfg'.format(title if title else 'kBmc',pid)
        screen_log_file='/tmp/.screen.{}_{}.log'.format(title if title else 'kBmc',pid)
        def _id_(title=None):
            scs=[]
            rc=rshell('''screen -ls''')
            #rc[0] should be 1, not 0
            for ii in rc[1].split('\n')[1:]:
                jj=ii.split()
                if len(jj) == 2 and jj[1] == '(Detached)':
                    if title:
                        zz=jj[0].split('.')
                        if '.'.join(zz[1:]) == title:
                            scs.append(jj[0])
                    else:
                        scs.append(jj[0])
            return scs

        def _kill_(title):
            ids=_id_(title)
            if len(ids) == 1:
                for i in range(0,10):
                    rc=rshell('''screen -X -S {} quit'''.format(ids[0]))
                    if rc[0] == 0:
                        if os.path.isfile(screen_tmp_file): os.unlink(screen_tmp_file)
                        if os.path.isfile(screen_log_file): os.unlink(screen_log_file)
                        return True
                    time.sleep(0.5)
            return False

        def _log_(title,cmd):
            omsg=''
            with open(screen_tmp_file,'w') as f:
                f.write('''logfile {}\nlogfile flush 0\nlog on\n'''.format(screen_log_file))
            if os.path.isfile(screen_tmp_file):
                mm,msg=self.get_cmd_module_name('ipmitool')
                if not mm:
                    if os.path.isfile(screen_tmp_file): os.unlink(screen_tmp_file)
                    return False,msg
                cmd_str_dict=mm.cmd_str(cmd,passwd=self.passwd)
                if cmd_str_dict[0]:
                    ok,ipmi_user,ipmi_pass=self.find_user_pass()
                    if not ok:
                        if os.path.isfile(screen_tmp_file): os.unlink(screen_tmp_file)
                        return False,'IPMI User or Password not found'
                    base_cmd=sprintf(cmd_str_dict[1]['base'],**{'ip':self.ip,'user':ipmi_user,'passwd':ipmi_pass})
                    cmd_str='''{} {}'''.format(base_cmd[1],cmd_str_dict[1].get('cmd'))
                rc=rshell('''screen -c {} -dmSL {} {}'''.format(screen_tmp_file,FixApostrophe(title),cmd_str))
                if rc[0] == 0:
                    for ii in range(0,50):
                        if os.path.isfile(screen_log_file):
                            os.unlink(screen_tmp_file)
                            return True,'log file found'
                        time.sleep(0.2)
                elif rc[0] == 127:
                    omsg=rc[2]
            else:
                omsg='can not create {} file'.format(screen_tmp_file)
            if os.path.isfile(screen_tmp_file): os.unlink(screen_tmp_file)
            if os.path.isfile(screen_log_file): os.unlink(screen_log_file)
            return False,msg

        def _info_():
            enable=False
            channel=1
            rate=9600
            port=623
            mm,msg=self.get_cmd_module_name('ipmitool')
            if not mm:
                return enable,rate,channel,port,'~~~ console=ttyS1,{}'.format(rate)
            rc=self.run_cmd(mm.cmd_str("""sol info""",passwd=self.passwd))
            if krc(rc,chk=True):
                for ii in rc[1][1].split('\n'):
                    ii_a=ii.split()
                    if ii_a[0] == 'Enabled' and ii_a[-1] == 'true':
                        enable=True
                    elif ii_a[0] == 'Volatile':
                        if '.' in ii_a[-1]:
                            try:
                                rate=int(float(ii_a[-1]) * 1000)
                            except:
                                pass
                        else:
                            try:
                                rate=int(ii_a[-1])
                            except:
                                pass
                    elif ii_a[0] == 'Payload':
                        if ii_a[1] == 'Channel':
                            try:
                                channel=int(ii_a[-2])
                            except:
                                pass
                        elif ii_a[1] == 'Port':
                            try:
                                port=int(ii_a[-1])
                            except:
                                pass
            return enable,rate,channel,port,'~~~ console=ttyS1,{}'.format(rate)

        def last_string(src,mspace=10):
            if isinstance(src,str):
                bk=0
                for i in range(len(src)-1,0,-1):
                    if src[i] == ' ':
                        bk+=1
                    else:
                        if bk > mspace:
                            break
                        bk=0
                if bk > mspace:
                    return src.split(''.join([' ' for i in range(0,bk)]))[-1]
            return src

        def _monitor_(title,find=[],timeout=600,session_out=30,stdout=False):
            # Linux OS Boot (Completely kernel loaded): find=['initrd0.img','\xff']
            # PXE Boot prompt: find=['boot:']
            # PXE initial : find=['PXE ']
            # DHCP initial : find=['DHCP']
            # PXE Loading : find=['pxe... ok','Trying to load files']
            # ex: aa=screen(cmd='monitor',title='test',find=['pxe... ok','Trying to load files'],timeout=300)
            # find:
            # - OR:  ('a','b','c') => found 'a' or 'b' or 'c' then pass
            # - AND: ['a','b','c'] => found all of 'a','b','c' then pass
            if not isinstance(title,str) or not title:
                return False,'no title'
            scr_id=_id_(title)
            if scr_id:
                return False,'Already has the title at {}'.format(scr_id)
            if _info_()[0] is False:
                return False,'The BMC is not support SOL function now. Please check up the BIOS or BMC'
            ok,msg=_log_(title,'sol activate')
            if not ok:
                _kill_(title)
                return False,msg
            mon_line=0
            mon_line_len=0
            old_mon_line=-1
            found=0
            find_num=len(find)
            Time=TIME()
            sTime=TIME()
            old_end_line=''
            if isinstance(find,str): find=[find]
            find_type='or' if isinstance(find,tuple) else 'and'
            find=list(find)
            sp_sp=[]
            while True:
                if not os.path.isfile(screen_log_file):
                    if sTime.Out(session_out):
                        _kill_(title)
                        return False,'Lost log file({})'.format(screen_log_file)
                    time.sleep(1)
                    continue
                with open(screen_log_file,'rb') as f:
                    tmp=f.read()
                tmp=CleanAnsi(Str(tmp))
                if '\x1b' in tmp:
                    tmp_a=tmp.split('\x1b')
                elif '\r\n' in tmp:
                    tmp_a=tmp.split('\r\n')
                elif '\r' in tmp:
                    tmp_a=tmp.split('\r')
                else:
                    tmp_a=tmp.split('\n')
                tmp_n=len(tmp_a)
                # Time Out
                if self.cancel():
                    if old_end_line:
                        return 0,old_end_line
                    return 0,tmp_a[mon_line-1]
                if Time.Out(timeout):
                    printf('Monitoring timeout({} sec)'.format(timeout))
                    _kill_(title)
                    if old_end_line:
                        return False,old_end_line
                    return False,tmp_a[mon_line-1]
                # Analysis log
                for ii in range(mon_line,tmp_n):
                    if stdout:
                        last_mon_line_end=last_string(tmp_a[ii],mspace=10)
                        if last_string(old_end_line,mspace=10) != last_mon_line_end:
                            printf(last_mon_line_end)
                    
                    if find: # check stop condition
                        for ff in range(0,find_num):
                            find_i=find[ff]
                            found_i=tmp_a[ii].find(find_i)
                            if found_i < 0:
                                if find_type == 'and' and (ff > 0 or ff == find_num):
                                    del find[ff-1]
                                    find_num=find_num-1
                                if find_type == 'or':
                                    continue # keep check next items
                                else:
                                    break #if can not find first item then no more find
                            found+=1
                            if find_type == 'or':
                                _kill_(title)
                                return True,'Found requirement {}'.format(find_i)
                            else:
                                if found >= find_num:
                                    _kill_(title)
                                    if stdout: printf('Found all requirements:{}'.format(find))
                                    return True,'Found all requirements:{}'.format(find)
                    # If not update any screen information then kill early session
                    if mon_line == tmp_n-1 and mon_line_len == len(tmp_a[tmp_n-1]):
                        if 'SOL Session operational' in old_end_line:
                            #If SOL Session operational message only then send <Enter> key
                            # control+c : "^C", Enter: "^M", any command "<linux command> ^M"
                            rshell('screen -S {} -p 0 -X stuff "^M"'.format(title))
                        elif 'SOL Session operational' in tmp_a[mon_line-1]:
                            # If BIOS initialization then increase session out time to 480(8min)
                            #if not old_end_line or old_end_line_end not in ['Initialization','initialization','Started','connect','Presence','Present']:
                            old_end_line_end=last_string(old_end_line,mspace=10)
                            last_mon_line_end=last_string(tmp_a[mon_line-1],mspace=10)
                            if not old_end_line or old_end_line_end == last_mon_line_end:
                                #session_out=timeout
                                if sTime.Out(session_out):
                                    msg='maybe not updated any screen information'
                                    if stdout: printf('{} (over {}seconds)'.format(msg,session_out))
                                    _kill_(title)
                                    if old_end_line:
                                        return False,old_end_line_end
                                    #return False,tmp_a[mon_line-1]
                                    return False,last_mon_line_end
                        elif old_end_line and old_end_line == tmp_a[-1]:
                            if sTime.Out(session_out):
                                _kill_(title)
                                if old_end_line:
                                    return False,old_end_line
                        time.sleep(1)
                        break 
                    else:
                        sTime.Reset()
                if tmp_n > 0:
                    mon_line=tmp_n -1
                else:
                    mon_line=tmp_n
                old_end_line=tmp_a[mon_line]
                mon_line_len=len(old_end_line)
                time.sleep(1)
            _kill_(title)
            return False,None
        if cmd == 'info':
            return _info_()
        elif cmd == 'id':
            return _id_(title),None
        elif cmd == 'kill':
            if title: return _kill_(title)
            return False,None
        elif cmd == 'console':
            mm,msg=self.get_cmd_module_name('ipmitool')
            if not mm:
                return False,msg
            cmd_str_dict=mm.cmd_str('sol activate',passwd=self.passwd)
            if cmd_str_dict[0]:
                ok,ipmi_user,ipmi_pass=self.find_user_pass()
                if not ok:
                    return False,'IPMI User or Password not found'
                base_cmd=sprintf(cmd_str_dict[1]['base'],**{'ip':self.ip,'user':ipmi_user,'passwd':ipmi_pass})
                cmd_str='{} {}'.format(base_cmd[1],cmd_str_dict[1].get('cmd'))
                rc=rshell(cmd_str,interactive=True)
                return True if Get(rc,0)==0 else False,Get(rc,1)
            return False,'Command not found'
        else:
            return _monitor_(title,find,timeout,session_out,stdout)

#    def ping(self,host=None,**opts):
#        if host is None: host=self.ip
#        if 'cancel_func' not in opts:
#            opts['cancel_func']=self.cancel
#        opts['count']=1
#        sping=ping(host,**opts)
#        if sping:
#            return True
#        else:
#            if 'timeout' not in opts: opts['timeout']=1200
#            printf(' Check network of IP({}) (timeout:{})'.format(host,opts.get('timeout',1200)),log=self.log,log_level=4,dsp='f')
#            return ping(host,**opts)

      

##############
# Example)
# bmc=kBmc.kBmc(ipmi_ip,ipmi_user,ipmi_pass,test_pass=['ADMIN','Admin'],test_user=['ADMIN','Admin'],timeout=1800,cmd_module=[Ipmitool(),Smcipmitool(smc_file=smc_file)])
# or 
# bmc=kBmc.kBmc(ip=ipmi_ip,user=ipmi_user,passwd=ipmi_pass,test_pass=['ADMIN','Admin'],test_user=['ADMIN','Admin'],timeout=1800,smc_file=smc_file)
# or 
# env={'ip':<ip>,'user':<user>,'passwd':<passwd>,'smc_file':<smc file>}
# bmc=kBmc.kBmc(env)
#
# bmc.power('status')
# bmc.power('off')
# bmc.is_up()
# bmc.bootorder(mode='pxe',ipxe=True,persistent=True,force=True)
# bmc.is_up()
# bmc.bootorder()
# bmc.summary()
# bmc.is_admin_user()
# bmc.lanmode()
# bmc.__dict__
# bmc.get_mac()
# bmc.get_eth_mac()
# bmc.reset()
