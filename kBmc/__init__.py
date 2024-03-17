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
# True     : Good, Doing result is good
# False    : False, Doing result is fail
# None     : Not bad, Nothing do
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
        cmd_a=Split(cmd)
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
        cmd_a=Split(cmd)
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
        if isinstance(self.smc_file,str) and Get(Split(os.path.basename(self.smc_file),'.'),-1) == 'jar':
            return True,{'base':'''sudo java -jar %s {ip} {user} %s{passwd}%s '''%(self.smc_file,sym,sym),'cmd':'''%s'''%(' '.join(cmd_a))},None,self.return_code,None
        else:
            return True,{'base':'''%s {ip} {user} %s{passwd}%s '''%(self.smc_file,sym,sym),'cmd':'''%s'''%(' '.join(cmd_a))},None,self.return_code,None

class Redfish:
    #ref: https://www.supermicro.com/manuals/other/redfish-ref-guide-html/Content/general-content/available-apis.htm
    #/redfish/v1/Managers/1/EthernetInterfaces/ToHost : RedfishHI
    #/redfish/v1/Managers/1/EthernetInterfaces/1      : BMC
    def __init__(self,**opts):
        self.power_on_tag='¯'
        self.power_up_tag='∸'
        self.power_off_tag='_'
        self.power_down_tag='⨪'
        self.power_unknown_tag='·'
        self.__name__='redfish'
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
        self.timeout=opts.get('timeout',1800)
        self.cancel_func=opts.get('cancel_func',opts.get('stop_func',None))
        self.bmc=opts.get('bmc')
        if self.bmc:
            self.user=self.bmc.__dict__['user'] 
            self.passwd=self.bmc.__dict__['passwd']
            self.host=self.bmc.__dict__['ip']
            self.pxe_boot_mac=self.bmc.__dict__['eth_mac']
            self.log=opts.get('log',self.bmc.__dict__['log'])
        else:
            self.user=opts.get('user','ADMIN')
            self.passwd=opts.get('passwd','ADMIN')
            self.host=opts.get('host',opts.get('ip'))
            self.pxe_boot_mac=opts.get('pxe_boot_mac')
            self.log=opts.get('log',None)

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
        if not isinstance(cmd,str): return False
        if not host: host=self.host
        if not ping(host,timeout=1800):
            printf("ERROR: Can not access the ip({}) over 30min.".format(host),log=self.log)
            return False,"ERROR: Can not access the ip({}) over 30min.".format(host)
        err_msg='Redfish Request Error'
        for i in range(0,2):
            data = WEB().Request(self.Cmd(cmd,host=host),auth=(self.user, self.passwd))
            if data[0]:
                if data[1].status_code == 200:
                    try:
                        return True,json.loads(data[1].text)
                    except:
                        if isinstance(data[1].text,str) and 'unauthorized' in data[1].text:
                            if self.bmc:
                                if self.bmc.find_user_pass()[0] is True:
                                    continue
                        err_msg=data[1].text
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
                        if isinstance(err_msg,str) and 'unauthorized' in err_msg:
                            if self.bmc:
                                if self.bmc.find_user_pass()[0] is True:
                                    continue
                        err_msg=data[1].text
                        return False, err_msg
                except:
                    if isinstance(data[1].text,str) and 'unauthorized' in data[1].text:
                        if self.bmc:
                            if self.bmc.find_user_pass()[0] is True:
                                continue
                    err_msg=data[1].text
                    return False,err_msg
        msg='Redfish Request : {}'.format(err_msg)
        printf(msg,log=self.log,mode='d')
        return False,msg

    def Post(self,cmd,host=None,json=None,data=None,files=None,mode='post',retry=3):
        if not host: host=self.host
        if not ping(host,timeout=1800):
            printf("ERROR: Can not access the ip({}) over 30min.".format(host),log=self.log)
            return False
        if not isinstance(cmd,str):
            printf("ERROR: Not support command({})".format(cmd),log=self.log)
            return False
        url=self.Cmd(cmd,host=host)
        #patch then need the power on
        if mode == 'patch':
            if not json and not data:
                return None #No data. So return None
            if self.Power() == 'off':
                if not self.Power('on',up=30,sensor=True):
                    printf("ERROR: Required power ON for the command, but can't power ON the system. Please look at the BMC or Redfish for power",log=self.log)
                    return False
        printf('Post:\n - url:{}\n - mode:{}\n - data:{}\n - json:{}\n - file:{}'.format(url,mode,data,json,files),log=self.log,mode='d')
        for i in range(0,retry):
            data = WEB().Request(url,auth=(self.user, self.passwd),mode=mode,json=json,data=data,files=files)
            printf(' - code:{}\n - msg:{}'.format(data[1].status_code,data[1].text),no_intro=None,log=self.log,mode='d')
            #Password Error then....
            if isinstance(data[1].text,str) and 'unauthorized' in data[1].text:
                if self.bmc:
                    if self.bmc.find_user_pass()[0] is True:
                        continue
            if data[0]:
                try:
                    tmp=FormData(data[1].text)
                except:
                    pass
                if isinstance(tmp,dict):
                    # sometimes, success with 202 code or maybe others(??)
                    if IsIn(next(iter(tmp)),['Success','Accepted']): #OK
                        if mode == 'patch':# if patch command then reset the power to apply
                            time.sleep(5)
                            return self.Power('reset',up=30,sensor=True)
                        return True #OK
                    if IsIn(next(iter(tmp)),['error']): #Error
                        mm= tmp.get('error',{}).get('@Message.ExtendedInfo')[-1].get('Message')
                        if isinstance(mm,str) and ('temporarily unavailable' in mm and 'Retry in  seconds' in mm) or ('Bios setting file already exists' in mm):
                            #Retry
                            # This error message required reset the power to flushing the redfish's garbage configuration
                            self.Power('reset',up=30,sensor=True)
                            #printf('.',end='',log=self.log)
                            printf('.',direct=True,log=self.log)
                            continue
                if data[1].status_code == 200: #OK
                    if mode == 'patch': # if patch command then reset the power to apply
                        time.sleep(5)
                        return self.Power('reset',up=30,sensor=True)
                    return True
                #Fail
                printf('ERROR({}:{}):{}'.format(mode,data[1].status_code,data[1].text),log=self.log)
                break
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

    def SystemReadyState(self,thermal=False):
        #it can read the Redfish's Thermal data when OS is running
        #ipmitool's sensor data can read when the system's CPU is ready
        if thermal:
            ok,aa=self.Get('Chassis/1/Thermal')
            if not ok:
#                printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1,mode='d')
                return False #Error
            if isinstance(aa,dict):
                for ii in aa.get('Temperatures',[]):
                    if ii.get('PhysicalContext') == 'CPU':
                        try:
                            return int(ii.get('ReadingCelsius')) #ON
                        except:
                            pass
        else:
            ok,aa=self.Get('Systems/1')
            if not ok:
#                printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1,mode='d')
                return False #Error
            if isinstance(aa,dict):
                #The hardware initialization finish / ready state
                #Same as ipmitool's sensor data readable step
                if IsIn(aa.get('BootProgress',{}).get('LastState'),['SystemHardwareInitializationComplete']):
                    return 'on' #ON
        return None # power off state

    def onoff_state(self,cmd):
        if IsIn(cmd,['on','up']):
            return 'on'
        elif IsIn(cmd,['off','ForceOff','shutdown','GracefulShutdown']):
            return 'off'

    def get_current_power_state(self):
        #return : on/off/unknown
        ok,aa=self.Get('Systems/1')
        if not ok:
#            printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1,mode='d')
            return False
        current_power=self.onoff_state(Get(aa,'PowerState'))
        if current_power is None:
            ok,aa=self.Get('Managers/1/Oem/Supermicro/SmartPower')
            current_power=self.onoff_state(Get(aa,'PowerState'))
        if current_power is None:
            return 'unknown'
        return current_power

    def IsUp(self,timeout=600,keep_up=0,sensor=False,sensor_temp=False):
        up_init=None
        Time=TIME()
        UTime=TIME()
        while not Time.Out(timeout):
            stat=self.power_unknown_tag
            if sensor:
                mon=self.SystemReadyState(thermal=sensor_temp)
            else:
                mon=self.get_current_power_state()
            if mon is False:
                return False
            elif mon in [None,'off','unknown']:
                UTime.Reset()
                if mon == 'unknown':
                    stat=self.power_unknown_tag
                else:
                    stat=self.power_off_tag
            else:
                if keep_up > 0:
                    if UTime.Out(keep_up): return True
                    stat=self.power_on_tag
                else:
                    return True
            printf(stat,direct=True,log=self.log,log_level=1)
            time.sleep(3)
        return None

    def IsDown(self,timeout=300,keep_down=0,sensor=False,sensor_temp=False):
        Time=TIME()
        DTime=TIME()
        while not Time.Out(timeout):
            stat=self.power_unknown_tag
            if sensor:
                mon=self.SystemReadyState(thermal=sensor_temp)
            else:
                mon=self.get_current_power_state()
            if mon is False:
                return False
            elif mon in [None,'off']:
                if keep_down > 0:
                    if DTime.Out(keep_down): return True
                    stat=self.power_off_tag
                else:
                    return True
            else:
                if mon == 'unknown':
                    stat=self.power_on_tag
                else:
                    stat=self.power_unknown_tag
                DTime.Reset()
            printf(stat,direct=True,log=self.log,log_level=1)
            time.sleep(3)
        return None

    def Power(self,cmd='status',**opts):
        pxe=opts.get('pxe',False)
        pxe_keep=opts.get('pxe_keep',False)
        uefi=opts.get('uefi',False)
        up=opts.get('up',opts.get('sensor_up',0))
        down=opts.get('down',opts.get('sensor_down',0))
        sensor=opts.get('sensor',False)
        sensor_temp=opts.get('sensor_temp',False)
        timeout=opts.get('timeout',1800)
        silent_status_log=opts.get('silent_status_log',True)
        def cmd_result(cmd):
            if IsIn(cmd, ['on','up','reboot','reset','off_on','ForceRestart','GracefulRestart','restart','cycle']):
                return 'on'
            elif IsIn(cmd, ['off','shutdown','ForceOff','GracefulShutdown']):
                return 'off'

        def rf_power_json_cmd(cmd):
            if IsIn(cmd,['on','up']):
                return 'On'
            elif IsIn(cmd,['off','ForceOff']):
                return 'ForceOff'
            elif IsIn(cmd,['shutdown','GracefulShutdown']):
                return 'GracefulShutdown'
            elif IsIn(cmd,['reset','cycle','ForceRestart']):
                return 'ForceRestart'
            elif IsIn(cmd,['reboot','GracefulRestart','restart']):
                return 'GracefulRestart'

        def _power_(cmd,retry=4,monitor_timeout=300):
            mt=TIME()
            mot=TIME()
            ok=None
            for i in range(0,retry):
                aa=self.Post('/Systems/1/Actions/ComputerSystem.Reset',json={'Action': 'Reset', 'ResetType': rf_power_json_cmd(cmd)})
                if aa is False: # Retry
                    ok=False #error
                    printf('.',log=self.log,direct=True,log_level=1)
                    time.sleep(5)
                    continue
                # reset group command
                if IsIn(cmd,['reset','cycle','reboot','restart','ForceRestart']):
                    #check off state
                    off_state=False
                    for x in range(0,20):
                        if self.SystemReadyState() is None:
                            off_state=True
                            break
                        printf('.',log=self.log,direct=True,log_level=1)
                        time.sleep(3)
                    if not off_state:
                        continue # retry
                mt.Reset()
                mot.Reset()
                while not mt.Out(monitor_timeout):
                    cps=self.get_current_power_state()
                    if cps == cmd_result(cmd):
                        return True
                    elif IsIn(cmd,['reset','cycle','reboot','restart','ForceRestart']) and cps == 'off':
                        #If reset command didn't power on after off then manually power on again
                        if mot.Out(60):
                            self.Post('/Systems/1/Actions/ComputerSystem.Reset',json={'Action': 'Reset', 'ResetType': rf_power_json_cmd('on')})
                            mot.Reset()
                    printf('.',log=self.log,direct=True,log_level=1)
                    time.sleep(5)
            return ok
        current_power=self.get_current_power_state()
        if IsIn(cmd,['status','state']):
            return current_power
        # working for defined command only
        if IsIn(cmd,['on','up','off','shutdown','reboot','reset','off_on','ForceOff','GracefulShutdown','ForceRestart','GracefulRestart','restart','cycle']):
            if not pxe and self.onoff_state(cmd) == current_power: return True
            #Do Power command
            if cmd == 'off_on': #special command
                off_s=_power_('off')
                if not off_s:
                    return off_s # False:Error, None: fail command
                cmd='on'
            #Set PXE Boot
            if pxe:
                self.Boot(boot='pxe',mode='Legacy' if uefi is False else 'UEFI',keep='keep' if pxe_keep else 'once')
                #pxe_str='ipxe' if uefi is True else 'pxe'
                #if pxe_keep:
                #    self.Boot(boot=pxe_str,keep='keep')
                #else:
                #    self.Boot(boot=pxe_str)
            # do power cmd
            rt=_power_(cmd)
            if rt:
                if cmd_result(cmd) == 'on':
                    if up >0:
                        #True: up, None: down, False: Error
                        return self.IsUp(timeout=timeout,keep_up=up,sensor=sensor,sensor_temp=sensor_temp)
                else:
                    if down > 0:
                        #True: down, None: up, False: Error
                        return self.IsDown(timeout=timeout,keep_down=down,sensor=sensor,sensor_temp=sensor_temp)
            return rt # False:Error, None: fail command
        else:
            if cmd == 'ID_LED': #Get ID_LED status
                ok,aa=self.Get('Chassis/1')
                if not ok:
#                    printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1,mode='d')
                    return False
                if isinstance(aa,dict):
                    return aa.get('IndicatorLED')
            elif cmd == 'ID_ON':
                #Turn on ID_LED
                pass
            elif cmd == 'ID_OFF':
                #Turn off ID_LED
                pass
            else: #Information
                naa={'status':self.get_current_power_state()}
                ok,aa=self.Get('Managers/1/Oem/Supermicro/SmartPower')
                if ok and isinstance(aa,dict):
                    naa['max']=aa.get('MaxPower')
                    naa['cap']=aa.get('PowerCapping')
                ok,aa=self.Get('Chassis/1/Power')
                if ok and isinstance(aa,dict):
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
    
    def PXEMAC(self,timeout=300):
        #if it has multiplue PXE bootable mac then try next pxe boot id when next_pxe_id=# (int number)
        #B13
        Time=TIME()
        while not Time.Out(timeout):
            ok,aa=self.Get('Systems/1/Oem/Supermicro/FixedBootOrder')
            if ok and isinstance(aa,dict):
                for i in Iterable(aa.get('UEFINetwork')):
                    for x in Split(i):
                        a=MacV4(x)
                        if a:
                            return a
            #Normal system case
            ok,aa=self.Get('Systems/1')
            if not ok or not isinstance(aa,dict):
#                printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1,mode='d')
                return False
            rf_key=aa.get('EthernetInterfaces',{}).get('@odata.id')
            if rf_key:
                ok,aa=self.Get(rf_key)
                if ok and isinstance(aa,dict):
                    rf_key=aa.get('Members',[{}])[0].get('@odata.id')
                    if rf_key:
                        ok,aa=self.Get(rf_key)
                        if ok and isinstance(aa,dict):
                            if aa.get('LinkStatus') == 'LinkUp':
                                return MacV4(aa.get('MACAddress'))
            printf('.',direct=True,log=self.log,log_level=1)
            time.sleep(3)

    def _Boot_BootSourceOverrideInfo(self):
        #Get Bootorder information
        #next: Next Boot
        #mode: UEFI, Regacy
        #enable: temporary boot order state
        #help: bootable order information
        #order: Settable Boot order in BIOS
        naa={}
        cmd='Systems/1'
        ok,aa=self.Get(cmd)
        if not ok or not isinstance(aa,dict):
#            printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1,mode='d')
            naa['error']=aa
            return naa
        naa['cmd']=cmd
        boot_info=aa.get('Boot',{})
        if boot_info:
            naa['next']=boot_info.get('BootNext')
            naa['mode']=boot_info.get('BootSourceOverrideMode')
            naa['1']=boot_info.get('BootSourceOverrideTarget')
            naa['enable']=boot_info.get('BootSourceOverrideEnabled')
            naa['order']=[]
            naa['help']={}
            if 'BootSourceOverrideMode@Redfish.AllowableValues' in boot_info: naa['help']['mode']=boot_info.get('BootSourceOverrideMode@Redfish.AllowableValues')
            if 'BootSourceOverrideTarget@Redfish.AllowableValues' in boot_info: naa['help']['boot']=boot_info.get('BootSourceOverrideTarget@Redfish.AllowableValues')
        return naa

    def _Boot_BiosBootInfo(self,pxe_boot_mac=None,next_pxe_id=False,ipv='v4',http=False):
        # Try to Special OEM BOOT ORDER first
        def SMC_OEM_SPECIAL_BOOTORDER(next_pxe_id=False):
            #if it has multiplue PXE bootable mac then try next pxe boot id when next_pxe_id=# (int number)
            #B13
            naa={}
            ok,fixed_boot_order_info=self.Get('Systems/1/Oem/Supermicro/FixedBootOrder')
            if not ok or not isinstance(fixed_boot_order_info,dict):
                return False
            naa['mode']=fixed_boot_order_info.get('BootModeSelected')
            pxe_boot_mac=[]
            for i in Iterable(fixed_boot_order_info.get('UEFINetwork')):
                for x in Split(i):
                    a=MacV4(x)
                    if a and a not in pxe_boot_mac:
                        pxe_boot_mac.append(a)
            naa['order']=fixed_boot_order_info.get('FixedBootOrder')
            for i in range(0,len(Iterable(naa['order']))):
                if isinstance(next_pxe_id,int) and not isinstance(next_pxe_id,bool) and next_pxe_id >= i:
                    continue
                for x in Split(naa['order'][i]):
                    a=MacV4(x)
                    if a and a in pxe_boot_mac:
                        naa['pxe_boot_id']=i
                        naa['pxe_boot_mac']=a
                        break
            return naa

        naa=SMC_OEM_SPECIAL_BOOTORDER(next_pxe_id=next_pxe_id)
        if isinstance(naa,dict): return naa
        #Get BIOS Boot order information
        cmd='Systems/1/Bios'
        naa={}
        ok,bios_info=self.Get(cmd)
        if not ok or not isinstance(bios_info,dict):
#            printf('Redfish ERROR: {}'.format(bios_info),log=self.log,log_level=1,mode='d')
            naa['error']=bios_info
            return naa
        #CMD
        if '@Redfish.Settings' in bios_info:
             naa['cmd']=bios_info.get('@Redfish.Settings',{}).get('SettingsObject',{}).get('@odata.id')
        else:
            naa['cmd']=cmd
        #PXE Boot Mac
        if pxe_boot_mac in [None,'00:00:00:00:00:00']: pxe_boot_mac=self.BaseMac().get('lan')
        naa['pxe_boot_mac']=MacV4(pxe_boot_mac)
     
        #Boot order
        boot_attr=bios_info.get('Attributes',{})
        if boot_attr:
            #BootMode # X11, X12, (X13,H13, B13, B2??)
            for ii in Iterable(boot_attr):
                if ii.lower().startswith('bootmodeselect'):
                    naa['mode']=boot_attr.get(ii)
                    naa['mode_name']=ii
                    break
                elif ii.startswith('BootSourceOverrideMode'):
                    naa['mode']=boot_attr.get(ii)
                    naa['mode_name']=ii
                    break

            #pxe boot protocol : http or https
            for ii in Iterable(boot_attr):
                if ii.startswith('HTTPSBootChecksHostname'):
                    if 'http' not in naa:  naa['http']={'ssl':False}
                    naa['http']['key']=ii
                    if boot_attr.get(ii) == 'Enabled': naa['http']['ssl']=True
                    break
            # X12,X13,H13,....
            #VideoOptionROM
            boot_id=0
            if 'support' not in naa: naa['support']={}
            for ii in Iterable(boot_attr):
                if ii.startswith('OnboardVideoOptionROM'):
                    naa['OnboardVideoOptionROM']=boot_attr[ii]
#                elif ii.startswith('AOC_'):
#                    naa['mode']=boot_attr[ii]
                elif ii.startswith('IPv4'): #Check Support PXE mode?
                    #It applied at redfish when PXE Boot prompt
                    #it is Advanced/Network Configuration/Network Stack
                    if 'HTTP' in ii:
                        if naa.get('http',{}).get('ssl',False):
                            naa['support']['https']={'key':[ii],'ver':['v4'],'enabled':[True if boot_attr[ii] == 'Enabled' else False]}
                        else:
                            naa['support']['http']={'key':[ii],'ver':['v4'],'enabled':[True if boot_attr[ii] == 'Enabled' else False]}
                    else:
                        naa['support']['pxe']={'key':[ii],'ver':['v4'],'enabled':[True if boot_attr[ii] == 'Enabled' else False]}
                elif ii.startswith('IPv6'): #Check Support PXE mode?
                    #It applied at redfish when PXE Boot prompt
                    #it is Advanced/Network Configuration/Network Stack
                    if 'HTTP' in ii:
                        if naa.get('http',{}).get('ssl',False):
                            if 'https' in naa['support']:
                                naa['support']['https']['key'].append(ii)
                                naa['support']['https']['ver'].append('v6')
                                naa['support']['https']['enabled'].append(True if boot_attr[ii] == 'Enabled' else False)
                            else:
                                naa['support']['https']={'key':[ii],'ver':['v6'],'enabled':[True if boot_attr[ii] == 'Enabled' else False]}
                        else:
                            if 'http' in naa['support']:
                                naa['support']['http']['key'].append(ii)
                                naa['support']['http']['ver'].append('v6')
                                naa['support']['http']['enabled'].append(True if boot_attr[ii] == 'Enabled' else False)
                            else:
                                naa['support']['http']={'key':[ii],'ver':['v6'],'enabled':[True if boot_attr[ii] == 'Enabled' else False]}
                    else:
                        if 'pxe' in naa['support']:
                            naa['support']['pxe']['key'].append(ii)
                            naa['support']['pxe']['ver'].append('v6')
                            naa['support']['pxe']['enabled'].append(True if boot_attr[ii] == 'Enabled' else False)
                        else:
                            naa['support']['pxe']={'key':[ii],'ver':['v6'],'enabled':[True if boot_attr[ii] == 'Enabled' else False]}
                elif ii.startswith('BootOption_'): # under X12 : boot order
                    if 'order' not in naa: naa['order']=[]
                    name=boot_attr[ii]
                    bb={'name':name,'id':boot_id,'key':ii}
                    bb['ip']='v6' if  'IPv6' in name else 'v4'
                    if  'EFI' in name:
                         bb['efi']=True
                    if  'HTTP' in name:
                         bb['http']=True
                    if  'PXE' in name:
                         bb['pxe']=True
                         bb['dhcp']=True
                         a=FIND(name).Find("(MAC:\w+)")
                         if a:
                             mac=MacV4(a[0][4:] if isinstance(a,list) else a[4:] if isinstance(a,str) else a)
                             bb['mac']=mac
                             if naa.get('pxe_boot_id') is None and mac == naa['pxe_boot_mac'] and bb.get('http',False) == http and bb.get('ip') == ipv and len(bb.get('key','').split('_')) == 2:
                                 naa['pxe_boot_id']=boot_id
                                 if boot_id == 0: naa['type']='http' if bb.get('http') is True  else 'pxe'
                    naa['order'].append(bb)
                    boot_id+=1
            if 'order' not in naa:
                #Boot order
                ok,aa=self.Get('Systems/1/BootOptions')
                if ok and isinstance(aa,dict):
                    membs=aa.get('Members',[{}])
                    if len(membs) == 1:
                        naa['mode']='Legacy'
                        naa['order']=['']
                        naa['pxe_boot_id']=None
                    else:
                        naa['mode']='UEFI'
                        naa['order']=[]
                        ix=0
                        for mem_i in Iterable(membs):
                            redirect=mem_i.get('@odata.id')
                            if isinstance(redirect,str) and redirect:
                                ok,aa=self.Get(redirect)
                                if not ok:
#                                    printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1,mode='d')
                                    naa['error']=aa
                                    return naa
                                if isinstance(aa,dict):
                                    if not aa.get('BootOptionEnabled',True): continue # enabled device or not.(old case, just support)
                                    name=aa.get('DisplayName','')
                                    bb={'name':name,'id':ix}
                                    #if 'UEFI Network Card' in name:# or 'UEFI PXE IP' in name:
                                    #    bb['efi']=True
                                    #    bb['pxe']=True
                                    #    bb['ip']='v4'
                                    #    bb['dhcp']=True
                                    #    a=FIND(name).Find("(MAC:\w+)")
                                    #    if a:
                                    #        mac=MacV4(a[0][4:] if isinstance(a,list) else a[4:] if isinstance(a,str) else a)
                                    #        bb['mac']=mac
                                    #        if naa.get('pxe_boot_id') is None and mac == naa['pxe_boot_mac']:
                                    #            naa['pxe_boot_id']=len(naa['order'])-1
                                    #else:
                                    if 'UEFI' in name:
                                        bb['efi']=True
                                    if 'PXE' in name:
                                        bb['pxe']=True
                                    elif 'HTTP' in name:
                                        bb['http']=True
                                    if 'UefiDevicePath' in aa:
                                        for x in Split(aa.get('UefiDevicePath'),'/'):
                                            if 'MAC(' in x:
                                                bb['mac']=MacV4(x.split(',')[0].split('(')[1])
                                            elif 'IP' in x:
                                                bb['ip']='v6' if 'IPv6' in x else 'v4'
                                                bb['dhcp']=True if 'DHCP' in x else False
                                    else:
                                        bb['dhcp']=True
                                        bb['ip']='v6' if 'IPv6' in name else 'v4'
                                        a=FIND(name).Find("(MAC:\w+)")
                                        if a:
                                            mac=MacV4(a[0][4:] if isinstance(a,list) else a[4:] if isinstance(a,str) else a)
                                            bb['mac']=mac
                                    naa['order'].append(bb)
                                    if naa['pxe_boot_mac'] in [None,'00:00:00:00:00:00'] and ix == 0 and bb.get('mac','A') != 'A' and bb.get('dhcp') is True and bb.get('ip') == ipv and bb.get('dhcp',False) == dhcp:
                                        naa['pxe_boot_id']=0
                                        naa['pxe_boot_mac']=bb['mac']
                                        naa['type']='http' if bb.get('http') is True  else 'pxe'
                                    elif naa.get('pxe_boot_id') is None and bb.get('mac','A')==naa.get('pxe_boot_mac','B') and bb.get('dhcp') is True and bb.get('ip') == ipv and bb.get('dhcp',False) == dhcp:
                                        naa['pxe_boot_id']=ix
                                        naa['type']='http' if bb.get('http') is True  else 'pxe'
                        ix+=1
        return naa

    def _Boot_NetworkBootOrder(self,pxe_boot_mac=None,http=False,ipv='v4'):
        #Systems/1/BootOptions (Boot) : BootOrder: Network Boot option's ordering, Not Boot order
        # Get Boot options and change it code
        boot_orders=[]
        ok,rt=self.Get('Systems/1/BootOptions')
        pxe_boot_mac=MacV4(pxe_boot_mac)
        printf('Set Network({}) BootOrder:'.format(pxe_boot_mac),log=self.log,log_level=1,mode='d')
        if ok:
             for x,i in enumerate(rt.get('Members',[])):
                 ok,rrt=self.Get(i.get('@odata.id'))
                 if ok:
                     if rrt.get('BootOptionEnabled'):
                         if (http and 'HTTP' in rrt.get('DisplayName')) or ('PXE' in rrt.get('DisplayName')):
                             if 'IP{}'.format(ipv) in rrt.get('DisplayName'):
                                 if pxe_boot_mac:
                                     a=FIND(rrt.get('DisplayName')).Find("(MAC:\w+)")
                                     if a:
                                          if pxe_boot_mac == MacV4(a[0][4:] if isinstance(a,list) else a[4:] if isinstance(a,str) else a):
                                              if x == 0: return None  #Already set
                                              boot_orders=[rrt.get('BootOptionReference')]+boot_orders
                                              continue
                                 else:
                                     boot_orders=[rrt.get('BootOptionReference')]+boot_orders
                                     continue
                     boot_orders.append(rrt.get('BootOptionReference'))
             if boot_orders:
                 boot_db={'Boot':{'BootOrder':boot_orders}}
                 return self.Post('Systems/1',json=boot_db,mode='patch')
             printf('ERROR: Not found boot order information',log=self.log,log_level=1,mode='d')
             return False
        else:
             printf('Not support Systems/1/BootOptions on this BMC',log=self.log,log_level=1,mode='d')
             return None

    def _Boot_Name(self,boot):
        ##  boot
        if IsIn(boot,['pxe','ipxe','uefi','efi']):
            return 'Pxe'
        elif IsIn(boot,['cd']):
            return 'Cd'
        elif IsIn(boot,['usb']):
            return 'Usb'
        elif IsIn(boot,['hdd']):
            return 'Hdd'
        elif IsIn(boot,['floppy']):
            return 'Floppy'

    def _Boot_Mode(self,mode):
        #if IsIn(mode,['uefi','efi','ipxe']):
        #    return 'UEFI'
        if IsIn(mode,['legacy','dual']):
            return 'Legacy'
        return 'UEFI'

    def _Boot_Keep(self,keep):
        ## Keep
        if IsIn(keep,[None,False,'disable','del','disabled']):
            return 'Disabled'
        elif IsIn(keep,['keep','continue','force','continuous','forever','permanente']):
            return 'Continuous'
        return 'Once'

    def _Boot_BootOrderCheck_(self,boot,mode,keep,pre=False,_o_=None):
        # Check current BIOS and Bootorder status is same as want value
        if not _o_: _o_=self._Boot_BootSourceOverrideInfo()
        boot_order_enable=_o_.get('enable','')
        if (pre is False and IsSame(keep,'Once') and boot_order_enable == 'Disabled') or (IsSame(self._Boot_Keep(keep),boot_order_enable) and boot_order_enable == 'Continuous'):
            if _o_.get('1','') == self._Boot_Name(boot) and self._Boot_Mode(mode) == _o_.get('mode'):
                msg='Redfish: Set BootOrder condition with {}, {}, {}'.format(self._Boot_Mode(mode),self._Boot_Name(boot),self._Boot_Keep(keep))
                printf(msg,log=self.log,mode='d')
                return True,msg
        return False,'Can not set bootsourceoverride'

    def _Boot_SetBootOrder(self,boot,mode='auto',keep='continue',_o_=None):
        ## Systems/1
        # Change keep,mode,boot parameter to Redfish's parameter name
        if IsIn(boot,['efi_shell','uefi_shell','shell']):
            mode='UEFI'
            boot='BiosSetup'
            keep='Continuous'
        else:
            if IsIn(boot,['bios','setup','biossetup','set']):
                mode='Legacy'
                boot='BiosSetup'
                keep='Once'
            else:
                mode=self._Boot_Mode(mode)
                boot=self._Boot_Name(boot)
                keep=self._Boot_Keep(keep)
        boot_db={'Boot':{
             'BootSourceOverrideEnabled':keep,
             'BootSourceOverrideMode':mode,
             'BootSourceOverrideTarget':boot
             }
        }
        if self._Boot_BootOrderCheck_(boot,mode,keep,pre=True,_o_=_o_)[0] is False:
            if self.Post('Systems/1',json=boot_db,mode='patch') is True:
                return self._Boot_BootOrderCheck_(boot,mode,keep)
        return None,'Redfish: ALready get same BootOrder condition'

    def _Boot_SetHTTP(self,_b_,mode,https=False,retry=3):
        setting_cmd=_b_.get('cmd',"Systems/1/Bios")
        chk='https' if https else 'http'
        boot_db={}
        if mode != _b_.get('mode'):
            if 'Attributes' not in boot_db: boot_db['Attributes']={}
            boot_db['Attributes'][_b_.get('mode_name')]=mode
        if chk not in _b_.get('support'):
            if https:
                if 'Attributes' not in boot_db: boot_db['Attributes']={}
                boot_db['Attributes']['HTTPSBootChecksHostname']='Enabled'
            else:
                if 'Attributes' not in boot_db: boot_db['Attributes']={}
                boot_db['Attributes']['HTTPSBootChecksHostname']='Disabled (WARNING: Security Risk!!)'
        if boot_db.get('Attributes'):
            for j in range(0,retry):
                if self.Post(setting_cmd,json=boot_db,mode='patch') in [True,None]:
                    _b_=BiosBootInfo()
                    if chk in _b_.get('support'):
                        return _b_ #Setup
                #printf('.',no_intro=True,log=self.log,log_level=1)
                printf('.',direct=True,log=self.log,log_level=1)
                time.sleep(10)
            return False # Not setup
        else:
            return _b_ #All Same

    def _Boot_BiosBootOrderCheck_(self,pxe_boot_mac,_b_=None):
        if not isinstance(_b_,dict): _b_=self._Boot_BiosBootInfo(pxe_boot_mac=pxe_boot_mac)
        if MacV4(pxe_boot_mac):
            if _b_.get('pxe_boot_mac') == pxe_boot_mac:
                if _b_.get('pxe_boot_id') == 0:
                    return True,'Same PXE Boot Condition({})'.format(pxe_boot_mac)
                return False,'Found mac({}) but boot order is low'.format(pxe_boot_mac)
            return False,'NOT Found mac({}) on this system'.format(pxe_boot_mac)
        return False,'Input parameter pxe_boot_mac is not MAC Address({})'.format(pxe_boot_mac)

    def _Boot_SetBiosBootOrder(self,boot='pxe',mode='UEFI',pxe_boot_mac=None,http=False,https=False,ipv='v4',retry=3,_b_=None):
        pxe_boot_mac=MacV4(pxe_boot_mac)
        if not isinstance(_b_,dict): _b_=self._Boot_BiosBootInfo(pxe_boot_mac=pxe_boot_mac)
        if http: #HTTP stuff
            _b_=self.SetHTTP(_b_,mode,https=https,retry=3)
            if _b_ is False: return False,'Can not setup BootMODE or HTTP/HTTPS protocol'

        net_boot=self._Boot_NetworkBootOrder(pxe_boot_mac=pxe_boot_mac,http=http,ipv=ipv)
        if net_boot is False: #Error
            printf('Network Boot(PXE) setting Error: Not found Network Boot Source',log=self.log,log_level=1)
            return False,'Network Boot(PXE) setting Error: Not found Network Boot Source'
        else:
            if net_boot is None:
                 printf('Network Boot(PXE) setting : Not support on this BMC',log=self.log,log_level=1,mode='d')
            _b_=self._Boot_BiosBootInfo(pxe_boot_mac=pxe_boot_mac)
        #Exist

        ## Systems/1/Bios
        setting_cmd=_b_.get('cmd',"Systems/1/Bios")
        boot_db={}
        #Change BIOS Boot order (under X12)
        if pxe_boot_mac:
            if self._Boot_BiosBootOrderCheck_(pxe_boot_mac,_b_=_b_)[0] is True:
                return True,'Already Same PXE Boot Condition({})'.format(pxe_boot_mac)
        if _b_.get('pxe_boot_mac') and _b_.get('pxe_boot_id'):
            if _b_.get('pxe_boot_mac') == pxe_boot_mac:
                boot_db={'Attributes':{_b_.get('order')[0].get('key'):_b_.get('order')[_b_.get('pxe_boot_id')].get('name')}}
            else:
                for i in Iterable(_b_.get('order')):
                    if i.get('mac') == pxe_boot_mac and i.get('dhcp') is True and i.get('ip') == 'v4' and i.get('http',False) == http:
                        boot_db={'Attributes':{_b_.get('order')[0].get('key'):i.get('name')}}
                        break
        mode=self._Boot_Mode(mode)
        if mode != _b_.get('mode'):
            #Change BootMode(BootModeSelect)
            if 'Attributes' not in boot_db: boot_db['Attributes']={}
            boot_db['Attributes'][_b_.get('mode_name')]=mode
        if (http is None or http is True) and 'http' in _b_.get('support'):
            #Change Support (http) (IPv4HTTPSupport)
            if 'Attributes' not in boot_db: boot_db['Attributes']={}
            http_info=_b_.get('support').get('http')
            if 'v4' in http_info.get('ver',{}):
                v4_id=http_info.get('ver').index('v4')
                if http_info.get('enabled')[v4_id] is False:
                    boot_db['Attributes'][http_info.get('key')[v4_id]]='Enabled'
        if (http is None or http is False) and 'pxe' in _b_.get('support'):
            #Change Support (PXE) (IPv4PXESupport)
            if 'Attributes' not in boot_db: boot_db['Attributes']={}
            pxe_info=_b_.get('support').get('pxe')
            if 'v4' in pxe_info.get('ver',{}):
                v4_id=pxe_info.get('ver').index('v4')
                if pxe_info.get('enabled')[v4_id] is False:
                    boot_db['Attributes'][pxe_info.get('key')[v4_id]]='Enabled'

        if boot_db.get('Attributes'):
            for j in range(0,retry):
                if self.Post(setting_cmd,json=boot_db,mode='patch') in [True,None]:
                    if self._Boot_BiosBootOrderCheck_(pxe_boot_mac)[0] is True:
#                    binfo=self._Boot_BiosBootInfo(pxe_boot_mac=pxe_boot_mac)
#                    if binfo.get('pxe_boot_id') == 0:
                       return True,'Set {} Boot with {}'.format('HTTPS' if http and https else 'HTTP' if http else 'PXE',pxe_boot_mac)
                #printf('.',no_intro=True,log=self.log,log_level=1)
                #printf('.',no_intro=True,log=self.log,log_level=1)
                time.sleep(10)
            return False,'Can not set {} Boot at BIOS'.format('HTTPS' if http and https else 'HTTP' if http else 'PXE')
        return None,'Not found any updating parameters'

    def BootInfo(self,simple_mode=False,rf_boot_info=None):
        if not isinstance(rf_boot_info,dict):
            rf_boot_info={'order':self._Boot_BootSourceOverrideInfo(),'bios':self._Boot_BiosBootInfo(pxe_boot_mac=MacV4(pxe_boot_mac))}
            if not rf_boot_info['order'] and not rf_boot_info['bios']:
                #Redfish issue
                return False,'Redfish Issue'
        # Information
        if IsIn(simple_mode,[True,'simple']):
            bios_boot_info=rf_boot_info.get('bios')
            if 'error' in bios_boot_info: return bios_boot_info.get('error')
            if bios_boot_info: return True,bios_boot_info.get('mode')
        elif IsIn(simple_mode,['bios']):
            return True,rf_boot_info['bios']
        #elif IsIn(simple_mode,['order','bootsourceoverride','override','temp','temporary']):
        elif IsIn(simple_mode,['bootsourceoverride','override','temp','temporary']):
            return True,rf_boot_info['order']
        elif IsIn(simple_mode,['flags']):
            return True,'''Boot Flags :
   - BIOS {} boot
   - BIOS PXE Boot order : {}
   - Options apply to {}
   - Boot Device Selector : {}
   - Boot with {}
'''.format(rf_boot_info.get('bios',{}).get('mode'),rf_boot_info.get('bios',{}).get('pxe_boot_id'),'all future boots' if rf_boot_info.get('order',{}).get('enable') == 'Continuous' else rf_boot_info.get('order',{}).get('enable'),rf_boot_info.get('order',{}).get('1'),rf_boot_info.get('order',{}).get('mode'))
        else: #all
            #if IsIn(boot,'order'):
            if IsIn(simple_mode,['order']):
                return True,'''Boot Flags :
   - BIOS {} boot
   - BIOS PXE Boot order : {}
   - Options apply to {}
   - Boot Device Selector : {}
   - Boot with {}
'''.format(rf_boot_info.get('bios',{}).get('mode'),rf_boot_info.get('bios',{}).get('pxe_boot_id'),'all future boots' if rf_boot_info.get('order',{}).get('enable') == 'Continuous' else rf_boot_info.get('order',{}).get('enable'),rf_boot_info.get('order',{}).get('1'),rf_boot_info.get('order',{}).get('mode'))
            return True,rf_boot_info

    def Boot(self,boot=None,mode='UEFI',keep='once',simple_mode=False,pxe_boot_mac=None,force=False,set_bios_uefi=False,set_mode='auto',ipv='v4',http=False,https=False):
        # set_mode: auto(default: set override fail then bios cfg), ['order','bootoverride','temp','simple','temporary']: set override, others: BIOS CFG, [info,None]: show information
        # - info 
        #    simple_mode: bios, simple, ['bootsourceoverride','override','temp','temporary'], order, flags, None(default)
        # - common(BIOSCFG, Bootoverride): 
        #    mode : UEFI(default),Dual,Regacy
        #    boot : ['efi_shell','uefi_shell','shell','pxe','ipxe','cd','usb','hdd','floppy','bios','setup','biossetup','efi','uefi','set'], [None,unknown]: infomation
        # - BIOS CFG
        #    ipv  : IP Version: v4(default), v6
        #    http : pxe boot protocol : False(default: pxe), True: http
        #    https: http protocol : False(default: http), True: https
        #    pxe_boot_mac: set pxe boot device same as the pxe_boot_mac when muti devices
        # - Boot over ride 
        #    keep: once(default), [keep,permanente,continue,force,...]: continue,  disable
        #################################################
        # Setting 
        #Check
        if pxe_boot_mac is None: pxe_boot_mac=self.pxe_boot_mac
        rf_boot_info={'order':self._Boot_BootSourceOverrideInfo(),'bios':self._Boot_BiosBootInfo(pxe_boot_mac=MacV4(pxe_boot_mac))}
        if not rf_boot_info['order'] and not rf_boot_info['bios']:
            #Redfish issue
            return False,'Redfish Issue'
        if IsIn(boot,['efi_shell','uefi_shell','shell','pxe','ipxe','cd','usb','hdd','floppy','bios','setup','biossetup','efi','uefi','set','http','https']):
            if IsIn(boot,['ipxe','efi','uefi']):
                boot='pxe'
                mode='UEFI'
            elif IsIn(boot,['http']):
                boot='pxe'
                http=True
                https=False
                mode='UEFI'
            elif IsIn(boot,['https']):
                boot='pxe'
                http=True
                https=True
                mode='UEFI'
            #Check
            biosbootorder_check=self._Boot_BiosBootOrderCheck_(pxe_boot_mac,_b_=rf_boot_info['bios'])
            if biosbootorder_check[0] is True:
                return biosbootorder_check
            #Temporary Boot order
            if IsIn(set_mode,['auto','order','bootoverride','temp','simple','temporary']) or IsIn(boot,['efi_shell','uefi_shell','shell','cd','usb','hdd','floppy','bios','setup','biossetup','set']):
                rt=self._Boot_SetBootOrder(boot,mode,keep=keep)
                if IsIn(set_mode,['auto']):
                    if rt[0]: return rt
                    #If fail then set boot bios cfg
                else:
                    return rt
            #BIOS CFG Change
            return self._Boot_SetBiosBootOrder(boot,mode,pxe_boot_mac,http,https,ipv,_b_=rf_boot_info['bios'])
        else:
        # Information
            return self.BootInfo(simple_mode,rf_boot_info)

    def BmcVer(self):
        ok,aa=self.Get('UpdateService/FirmwareInventory/BMC')
        if not ok:
#            printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1,mode='d')
            return None
        if isinstance(aa,dict): return aa.get('Version')
        ok,aa=self.Get('Managers/1')
        if not ok:
#            printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1,mode='d')
            return None
        if isinstance(aa,dict): return aa.get('FirmwareVersion')

    def BiosVer(self):
        ok,aa=self.Get('UpdateService/FirmwareInventory/BIOS')
        if not ok:
#            printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1,mode='d')
            return None
        if isinstance(aa,dict): return aa.get('Version')
        ok,aa=self.Get('Systems/1')
        if not ok:
#            printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1,mode='d')
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
#            printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1,mode='d')
            return naa
        if isinstance(aa,dict):
            naa['bmc']=MacV4(Get(Split(aa.get('UUID'),'-'),-1))
        naa['lan']=self.PXEMAC()
        if not naa['lan']:
            ok,aa=self.Get('Systems/1')
            if not ok:
#                printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1,mode='d')
                return naa
            if isinstance(aa,dict):
                naa['lan']=MacV4(Get(Split(aa.get('UUID'),'-'),-1))
            if naa.get('lan') and naa['lan'] == naa.get('bmc'):
                rf_net=self.Network()
                for nid in Iterable(rf_net):
                    for pp in Iterable(rf_net[nid].get('port',{})):
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
#            printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1,mode='d')
            return naa
        if isinstance(aa,dict):
            for ii in Iterable(aa.get('Members',[])):
                ok,ai=self.Get(ii.get('@odata.id'))
                if not ok:
#                    printf('Redfish ERROR: {}'.format(ai),log=self.log,log_level=1,mode='d')
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
#                        printf('Redfish ERROR: {}'.format(port),log=self.log,log_level=1,mode='d')
                        return naa
                    if isinstance(port,dict):
                        for pp in Iterable(port.get('Members')):
                            ok,port_q=self.Get(pp.get('@odata.id'))
                            if not ok:
#                               printf('Redfish ERROR: {}'.format(port_q),log=self.log,log_level=1,mode='d')
                               return naa
                            naa[ai_id]['port'][port_q.get('Id')]={}
                            naa[ai_id]['port'][port_q.get('Id')]['mac']=port_q.get('AssociatedNetworkAddresses')[0]
                            naa[ai_id]['port'][port_q.get('Id')]['state']=port_q.get('LinkStatus')
        return naa

    def Memory(self):
        naa={}
        ok,aa=self.Get('Systems/1/Memory')
        if not ok:
#            printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1,mode='d')
            return naa
        if isinstance(aa,dict):
            for ii in Iterable(aa.get('Members',[])):
                ok,ai=self.Get(ii.get('@odata.id'))
                if not ok:
#                    printf('Redfish ERROR: {}'.format(ai),log=self.log,log_level=1,mode='d')
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
#            printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1,mode='d')
            return naa
        if isinstance(aa,dict):
            for ii in Iterable(aa.get('Members',[])):
                ok,ai=self.Get(ii.get('@odata.id'))
                if not ok:
#                    printf('Redfish ERROR: {}'.format(ai),log=self.log,log_level=1,mode='d')
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
#            printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1,mode='d')
            return naa
        naa['mac']={}
        if isinstance(aa,dict):
            naa['mac']['bmc']=MacV4(Get(Split(aa.get('UUID'),'-'),-1))
        ok,aa=self.Get('Systems/1')
        if not ok:
#            printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1,mode='d')
            return naa
        if isinstance(aa,dict):
            naa['mac']['lan']=MacV4(Get(Split(aa.get('UUID'),'-'),-1))
            naa['Model']=aa.get('Model')
            naa['SerialNumber']=aa.get('SerialNumber')
            naa['UUID']=aa.get('UUID')
        ok,aa=self.Get('Chassis/1')
        if not ok:
#            printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1,mode='d')
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


    def VirtualMedia(self,mode='floppy'):
        mode=mode.lower()
        info=[]
        ok,vv=self.Get('Managers/1/VirtualMedia')
        if not ok:
#            printf('Redfish ERROR: {}'.format(vv),log=self.log,log_level=1,mode='d')
            return False
        if isinstance(vv,dict):
            for ii in Iterable(vv.get('Members',[])):
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
#                        printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1,mode='d')
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
#                printf('Redfish ERROR: {}'.format(aa),log=self.log,log_level=1,mode='d')
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
                    if self.Post(rf_key,json={'Current interface':'HTML 5'},mode='patch') is False:
                        return False,'Can not set to HTML 5'
            else:
                rf_key='/Managers/1/IKVM'
        return False,'Can not login to the server'

    def ConsoleInfo(self):
        aa=self.Get('Systems/1')
        out={}
        if aa[0] is instance(aa[1],dict):
            for ii in Iterable(aa[1].get('SerialConsole')):
                if ii not in out: out[ii]={}
                if isinstance(aa[1]['SerialConsole'][ii],(dict,list)):
                    for jj in Iterable(aa[1]['SerialConsole'][ii]):
                        if jj in ['Port','ServiceEnabled']:
                            out[ii][jj]=aa[1]['SerialConsole'][ii][jj]
                else:
                    out[ii]=aa[1]['SerialConsole'][ii]
            gpc=aa[1].get('GraphicalConsole')
            if gpc:
                out[gpc.get('ConnectTypesSupported')[0]]={'Port':gpc.get('Port'),'ServiceEnabled':gpc.get('ServiceEnabled')}
        return out

    def McResetCold(self,keep_on=30):
        rc=self.Post('/Managers/1/Actions/Manager.Reset')
        if rc is True:
             time.sleep(5)
             printf("""Wait until response from BMC""",log=self.log,log_level=1,dsp='d')
             return ping(self.host,keep_good=keep_on,timeout=self.timeout,cancel_func=self.cancel_func,log=self.log)
        return rc

    def FactoryDefault(self,keep_on=30):
        rc=self.Post('/Managers/1/Actions/Oem/SmcManagerConfig.Reset')
        if rc is True:
            time.sleep(5)
            self.Power(cmd='on' if self.Power() == 'off' else 'reset' ,sensor_up=keep_on,sensor=True)
        return rc

    def LoadDefaultBios(self,keep_on=30): #Good
        rc=self.Post('/Systems/1/Bios/Actions/Bios.ResetBios')
        if rc is True:
            time.sleep(5)
            self.Power(cmd='on' if self.Power() == 'off' else 'reset' ,sensor_up=keep_on,sensor=True)
        return rc

    def FactoryDefaultBios(self):
        return LoadDefaultBios()

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
        self.default_passwd=Get(opts,['ipmi_dpass','dpasswd','default_password'],default='ADMIN',err=True,peel='force')
        self.org_passwd=opts.get('org_passwd',self.passwd)
        self.test_user=opts.get('test_user')
        if not self.test_user: self.test_user=['ADMIN','Admin','admin','root','Administrator']
        self.base_passwd=['ADMIN','Admin','admin','root','Administrator']
        self.test_passwd=opts.get('test_pass',opts.get('test_passwd',self.base_passwd))
        if not isinstance(self.test_passwd,list):
            self.test_passwd=self.base_passwd
        if self.user in self.test_user: self.test_user.remove(self.user)
        if self.passwd in self.test_passwd: self.test_passwd.remove(self.passwd)
        #Hard coding for ADMIN1234. So do not remove it
        if 'ADMIN1234' not in self.test_passwd: self.test_passwd.append('ADMIN1234')
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

    def CallRedfish(self,force=False,check=True,no_ipmitool=False,detail_log=False):
        if self.redfish or force:
            if force or check:
                # when it called from here and there. So too much logging
                if detail_log: printf("Check IP Address",log=self.log,log_level=1,dsp='d')
                ip=self.mac2ip(self.mac) if self.mac2ip and self.checked_ip is False and MacV4(self.mac) else '{}'.format(self.ip)
                if detail_log: printf("Check Ping to the IP({}):".format(ip),log=self.log,log_level=1,dsp='d',end='')
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
                        if ok is False:
                            printf("Can not find working user and password",log=self.log,log_level=1,dsp='e')
                            return False
                    rf=Redfish(bmc=self)
                    if krc(rf.Get('/Systems'),chk=True):
                        return rf
                    printf("Maybe not support redfish on this system",log=self.log,log_level=1,dsp='d')
                    return False
                    #if ok:
                    #    return Redfish(host=ip,user=user,passwd=passwd,log=self.log)
                    #else:
                    #    test_user=MoveData(self.test_user[:],self.user,to='first')
                    #    if not test_user: test_user=['ADMIN']
                    #    test_passwd=self.test_passwd[:]
                    #    test_passwd=MoveData(test_passwd,test_passwd[-1],to='first') # move last one
                    #    if self.upasswd: test_passwd=MoveData(test_passwd,self.upasswd,to='first') # move uniq passwd
                    #    if self.default_passwd : test_passwd=MoveData(test_passwd,self.default_passwd,to='first') # move default  passwd
                    #    if self.org_passwd: test_passwd=MoveData(test_passwd,self.org_passwd,to='first') # move original passwd
                    #    test_passwd=MoveData(test_passwd,self.passwd,to='first') # move current passwd
                    #    printf("Search User and Password in Redfish",log=self.log,mode='d')
                    #    for i_user in test_user:
                    #        for i in range(0,len(test_passwd)):
                    #            rf=Redfish(host=ip,user=i_user,passwd=test_passwd[i],log=self.log)
                    #            aa=rf.Get('/Systems')
                    #            if krc(aa,chk=True):
                    #                printf('.',no_intro=True,log=self.log)
                    #                printf("Found Redfish Login User&Password: {},{}".format(i_user,test_passwd[i]),log=self.log,log_level=1,mode='d')
                    #                return rf
                    #            printf(".",direct=True,log=self.log)
                    #            if i > 1 and i+1 % 2 == 0:
                    #                time.sleep(50)
                    #            else:
                    #                time.sleep(1)
                    #    printf("Can not find Redfish working user/password",log=self.log,log_level=1,dsp='w')
                    #    self.error(_type='user_pass',msg="Can not find Redfish working User/password")
                    #    return False
                else:
                    printf("Can not ping to {}".format(ip),log=self.log,log_level=1,dsp='e')
                    self.error(_type='net',msg="Can not ping to {}".format(ip))
                    return False
            else:
            #    return Redfish(host=self.ip,user=self.user,passwd=self.passwd,log=self.log)
                return Redfish(bmc=self)
        #Not support redfish
        return False

    def SystemReadyState(self,cmd_str,name):
        #ipmitool/smcipmitool's cpu temperature
        rrc=self.run_cmd(cmd_str)
        if krc(rrc,chk=True):
            for ii in Split(rrc[1][1],'\n'):
                ii_a=Split(ii,'|')
                find=''
                if name == 'smc' and len(ii_a) > 2:
                    find=Strip(ii_a[1]).upper()
                elif len(ii_a) > 5:
                    find=Strip(ii_a[0]).upper()
                else:
                    continue
                if '_' not in find and 'TEMP' in find and ('CPU' in find or 'SYSTEM ' in find):
                    if name == 'smc':
                        tmp=Strip(ii_a[2])
                        if tmp in ['N/A','Disabled','0C/32F']:
                            return 'down'
                        elif 'C/' in tmp and 'F' in tmp: # Up state
                            return 'up'
                        elif tmp == 'No Reading':
                            self.warn(_type='sensor',msg="Can not read sensor data")
                    else: #ipmitool
                        tmp=Strip(ii_a[3])
                        tmp2=Strip(ii_a[4])
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
            cpu_temp=rf.SystemReadyState()
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

        checked_redfish=opts.get('checked_redfish',False)
        # _: Down, ¯: Up, ·: Unknown sensor data, !: ipmi sensor command error
        out=['none','none','none'] # [Sensor(ipmitool/SMCIPMITool), Redfish, ipmitool/SMCIPMITool]
        if redfish:
            #Reduce checking redfish stuff when already verifyed
            rf=self.CallRedfish(check=False if checked_redfish else True)
            if rf:
                checked_redfish=True
                rt=rf.Power()
                if IsIn(rt,['on','off']):
                    out[1]=rt
                else:
                    out[1]='error'
        if tools:
            for mm in Iterable(self.cmd_module):
                rt=self.run_cmd(mm.cmd_str('ipmi power status',passwd=self.passwd))
                if krc(rt,chk=True):
                    aa=Split(rt[1][1])
                    if aa:
                        if IsIn(aa[-1],['on','off']):
                            out[2]=aa[-1]
                            break
        if sensor:
            for mm in Iterable(self.cmd_module):
                rt=self.SystemReadyState(mm.cmd_str('ipmi sensor',passwd=self.passwd),mm.__name__)
                out[0]='on' if rt == 'up' else 'off' if rt == 'down' else rt
                break 
        return out,checked_redfish

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
        def is_on_off(data,mode='a',sensor_time=None,sensor_off_time=420,before=None):
            #<sensor>,<redfish>,<ipmi/tool>
            # data: [Sensor data(ipmitool/smcipmitool), Redfish data, ipmitool/smcipmitool data)]
            if data[0] == data[1] and data[1] == data[2]: # All same data then return without any condition
                #return OFF/ON at sensor or auto mode
                return data[0],0
            if mode == 's':
                if not sensor_time: sensor_time=TIME().Int()
                if data[1] == 'off' and (data[1] == data[2] or data[0] == data[1]):
                    return 'off',sensor_time
                elif data[0] == 'off' or data[1] == 'off':
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
                        else:
                            #if data[1] == data[2] and data[1] =='on': #booting
                            if data[2] =='on': #booting
                                if IsIn(before,['on']): # reset command/suddenly changed state then got off state
                                    return 'off',sensor_time
                                return 'up',sensor_time
                    return 'off',sensor_time
                elif data[0] == 'on' or data[1] == 'on':
                    return 'on',sensor_time
            elif mode == 'a':
                if 'on' in data[1:]: return 'on',0 # anyone on then on 
                if 'off' in data[1:]: return 'off',0  # anyone off then off
            elif mode == 'r':
                if data[1] in ['on','off']: return data[1],0 # redfish output
            else:
                if data[2] in ['on','off']: return data[2],0 # cmd/ipmitool output
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
            keep_last_state_time=Int(opts.get('keep_on'),Int(opts.get('keep_last_state_time'),0))
            keep_error_state_time=Int(opts.get('keep_off'),Int(opts.get('keep_error_state_time'),0))
        elif 'keep_off' in opts and monitoring_state[-1] == 'off':
            keep_last_state_time=Int(opts.get('keep_off'),Int(opts.get('keep_last_state_time'),0))
            keep_error_state_time=Int(opts.get('keep_on'),Int(opts.get('keep_error_state_time'),0))
        else:
            keep_last_state_time=Int(opts.get('keep_last_state_time'),0)
            keep_error_state_time=Int(opts.get('keep_error_state_time'),0)

        #########################################
        #initialize data
        #########################################
        if not isinstance(data,dict): data={}
        if 'count' not in data: data['count']=0
        if 'stop' not in data: data['stop']=False
        if 'timeout' not in data: data['timeout']=timeout # default 1800(30min)
        if 'sensor_off_time' not in data: data['sensor_off_time']=Int(sensor_off_time,450) # Sensor monitoring timeout 
        if 'monitor_interval' not in data: data['monitor_interval']=Int(monitor_interval,5) # default 5
        if 'keep_last_state_time' not in data: data['keep_last_state_time']=keep_last_state_time
        if 'keep_error_state_time' not in data: data['keep_error_state_time']=keep_error_state_time
        if 'mode' not in data: data['mode']=mode if mode in ['s','a','r','t'] else 'a'
        #data monitoring initialize data (time, status)
        if 'init' not in data: data['init']={}
        curr_power_status,checked_redfish=get_current_power_status()
        #if 'config' not in data['init']: data['init']['config']={'time':TIME().Int(),'status':get_current_power_status()}
        if 'config' not in data['init']: data['init']['config']={'time':TIME().Int(),'status':curr_power_status}
        data['monitoring']=monitoring_state # want monitoring state
        data['monitored_status']={}
        before=None
        monitor_id=0
        monitoring_start_time=None
        monitoring_state=None
        data['remain_time']=data.get('timeout')
        is_on_off_time=None
        Time=TIME()
        before=None
        ss=''
        while True:
            data['count']+=1
            if data['init'].get('start',{}).get('time'):
                data['remain_time']=data.get('timeout') - (TIME().Int() - data['init'].get('config',{}).get('time'))
            if not 'start' in data.get('init',{}) and data.get('start') is True:
                #Start monitoring initialize data (time, status)
                #we can check time and status condition between defined bpm time and start monitoring
                curr_power_status,checked_redfish=get_current_power_status(checked_redfish=checked_redfish)
                #data['init']['start']={'time':TIME().Int(),'status':get_current_power_status()}
                data['init']['start']={'time':TIME().Int(),'status':curr_power_status}
            # Timeout
            if Time.Out(data['timeout']):
                A={}
                for i in Iterable(data['monitored_status']):
                    for j in Iterable(data['monitored_status'][i]):
                        A[j.get('time')]={i:j}
                B=[]
                data['monitored_order']=[]
                for i in sorted(A.items()):
                    B.append(next(iter(i[1])))

                a='-'.join(B)
                if a: a='-{}'.format(a)
                data['done']={TIME().Int():'Monitoring timeout({}sec){}'.format(data['timeout'],a)}
                data['done_reason']='timeout'
                data['symbol']=self.power_on_tag if B[-1] == 'on' else self.power_off_tag if B[-1] == 'off' else self.power_unknown_tag
                if status_log:
                    printf(data['symbol'],log=self.log,direct=True,log_level=1)
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
            curr_power_status,checked_redfish=get_current_power_status(checked_redfish=checked_redfish)
            on_off,is_on_off_time=is_on_off(curr_power_status,mode=data['mode'],sensor_time=is_on_off_time,sensor_off_time=data['sensor_off_time'],before=monitoring_state)
            if on_off not in data['monitored_status']: data['monitored_status'][on_off]=[]
            if monitoring_state == on_off: #same condition : update time
                data['monitored_status'][on_off][-1]['keep_time']=TIME().Int()
            else:
                #new conditioin/data:initial
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
                    printf(self.power_up_tag,log=self.log,direct=True,log_level=1)
                data['symbol']=self.power_up_tag
            elif on_off == 'dn':
                if status_log:
                    printf(self.power_down_tag,log=self.log,direct=True,log_level=1)
                data['symbol']=self.power_down_tag
            else:
                if status_log:
                    printf(self.power_unknown_tag,log=self.log,direct=True,log_level=1)
                data['symbol']=self.power_unknown_tag
            ################################################
            # if same condition then add to monitored status(Next step monitoring)
            if on_off == data['monitoring'][monitor_id]:
                if monitor_id < len(data['monitoring'])-1: monitor_id+=1
            ############################################
            # Suddenly wrong condition
            if data['keep_error_state_time']>0:
                 if data['monitoring'][monitor_id]  != on_off and on_off in data['monitored_status'] and (len(data['monitored_status']) > 1 if len(data['monitoring']) > 1 else True): #two more monitored state, but studdenly keep wrong(off/on) state then....
                     if on_off in ['on','off']:
                         #Is it end of state?
                         esst=True
                         for sst in Iterable(data['monitored_status']):
                             if sst == on_off: continue
                             if data['monitored_status'][sst][-1].get('keep_time') > data['monitored_status'][on_off][-1].get('time',0):
                                  esst=False
                                  break
                         if esst:
                             if data['monitored_status'][on_off][-1].get('keep_time',0)-data['monitored_status'][on_off][-1].get('time',0) > data['keep_error_state_time']:
                                 data['done']={TIME().Int():ss}
                                 data['done_reason']='fail'
                                 return
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
        for i in Iterable(data['monitored_status']):
            for j in Iterable(data['monitored_status'][i]):
                A[j.get('time')]={i:j}
        B=[]
        data['monitored_order']=[]
        for i in sorted(A.items()):
            B.append(i[1])
            data['monitored_order'].append(next(iter(i[1])))
        # Summary print condition
        if status_log and info is True:

            data_info='Monitor Start at {} with {}'.format(data['init']['start']['time'],data['monitoring'])
            for i in Iterable(B):
                i_name=next(iter(i))
                data_info=data_info+'\n{} detected at {} ({}sec)'.format(i_name,i.get(i_name).get('time'),i.get(i_name).get('keep_time')-i.get(i_name).get('time'))
            data_info=data_info+'\nkeep time of last state  : {}'.format(data.get('keep_last_state_time'))
            data_info=data_info+'\nFinished time  : {}'.format(next(iter(data.get('done'))))
            data_info=data_info+'\nFinished Reason: {} ({})'.format(data.get('done_reason'),data.get('done')[next(iter(data.get('done')))])
            printf(data_info,log=self.log,log_level=1)

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
                printf('Already running',log=self.log)
                return self.bgpm
            # if new monitoring then initialize data
            self.bgpm={'status':{},'repeat':0,'stop':False,'count':0,'start':start,'timeout':timeout,'cancel_func':self.cancel_func}
            self.bgpm['worker']=threading.Thread(target=self.power_status_monitor_t,args=(monitor_status,self.bgpm,keep_off,keep_on,sensor_on_monitor,sensor_off_monitor,monitor_interval,timeout,0,opts.get('mode','a')))
            self.bgpm['worker'].start()
            return self.bgpm
        else:
            #foreground should be different
            #act foreground then immediately start monitoring and return the output
            fgpm={'status':{},'repeat':0,'stop':False,'count':0,'start':True,'timeout':timeout,'cancel_func':self.cancel_func}
            self.power_status_monitor(monitor_status,fgpm,keep_off=keep_off,keep_on=keep_on,sensor_monitor=sensor_on_monitor,sensor_off_monitor=sensor_off_monitor,status_log=status_log,monitor_interval=monitor_interval,timeout=timeout,reset_after_unknown=reset_after_unknown,mode=opts.get('mode','a'))
            return fgpm

    def is_started_power_monitor(self,bpm=None):
        if isinstance(bpm,dict) and bpm.get('start') is True:
             if bpm.get('stop') is False and not bpm.get('done'): return True
        return False

    def check(self,mac2ip=None,cancel_func=None,trace=False,timeout=None):
        if cancel_func is None: cancel_func=self.cancel_func
        if timeout is None: timeout=self.timeout
        rc=False
        ip='{}'.format(self.ip)
        if self.checked_ip is False:
            if mac2ip:
                if not MacV4(self.mac):
                    mac_ok,mac_addr=self.get_mac(ip,user=self.user,passwd=self.passwd)
                    if mac_ok:
                        self.mac=mac_addr
                        #Already checked IP,user,passwd in get_mac()
                        return True,self.ip,self.user,self.passwd
                    else:
                        self.error(_type='mac',msg='Can not find BMC Mac address')
                        printf("Can not find BMC Mac address",log=self.log,log_level=1,mode='e')
                        return False,self.ip,self.user,self.passwd
                ip=mac2ip(self.mac)
                self.checked_port=False
        ping_rc=ping(ip,keep_good=0,timeout=timeout,log=self.log,cancel_func=cancel_func)
        if ping_rc is True:
            if self.checked_port is False:
                cc=False
                direct_print=False
                for i in range(0,10):
                    if IpV4(ip,port=self.port):
                        self.checked_ip=True
                        self.checked_port=True
                        cc=True
                        break
                    printf(".",log=self.log,direct=True)
                    direct_print=True
                    time.sleep(3)
                if direct_print: printf(".",no_intro=True,log=self.log,log_level=1)
                if cc is False:
                    printf("{} is not IPMI IP(2)".format(ip),log=self.log,log_level=1,dsp='e')
                    self.error(_type='ip',msg="{} is not IPMI IP(2)".format(ip))
                    return False,self.ip,self.user,self.passwd
            ok,user,passwd=self.find_user_pass(ip,trace=trace,cancel_func=cancel_func)
            if ok:
                #Update IP,User,Password
                if self.ip != ip:
                    printf('Update IP from {} to {}'.format(ip,self.ip),log=self.log,log_level=1,dsp='e')
                    self.ip=ip
                if self.user != user:
                    printf('Update User from {} to {}'.format(user,self.user),log=self.log,log_level=1,dsp='e')
                    self.user=user
                if self.passwd!= passwd:
                    printf('Update Password from {} to {}'.format(passwd,self.passwd),log=self.log,log_level=1,dsp='e')
                    self.passwd=passwd
                rc=True
        else:
            printf('Destination Host({}) Unreachable/Network problem'.format(self.ip),log=self.log,log_level=1,dsp='e')
            self.error(_type='net',msg='Destination Host({}) Unreachable/Network problem'.format(self.ip))
        return rc,self.ip,self.user,self.passwd

    def get_cmd_module_name(self,name):
        if isinstance(self.cmd_module,list):
            for mm in Iterable(self.cmd_module):
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
                        if Strip(data[j]).startswith('Boot Mode Select'):
                            sop=Get(Get(Strip(data[j]).split(),2,default='').split('='),1)
                            if sop == '02':
                                return 'DUAL','','',''
                            elif sop == '01':
                                return 'UEFI','','',''
                            elif sop == '01':
                                return 'LEGACY','','',''

        def find_boot_mode(data):
            data_a=Split(data,'\n')
            for i in range(0,len(data_a)):
                if '<?xml version' in data_a[i]:
                    return xml_find(data_a[i:])
                elif '[Advanced' in data_a[i]:
                    return flat_find(data_a[i:])

        # Boot mode can automatically convert iPXE or PXE function
        # if power handle command in here then use self.power(xxxx,lanmode=self.bmc_lanmode) code
        if isinstance(bioscfg,str):
            if os.path.isfile(bioscfg):
                with open(bioscfg,'rb') as f:
                    bioscfg=f.read()
        if isinstance(bioscfg,str) and bioscfg:
            found=find_boot_mode(Str(bioscfg))
            if found:
                return True,found
        return False,('','','','')

    def find_user_pass(self,ip=None,default_range=12,check_cmd='ipmi power status',cancel_func=None,error=True,trace=False,extra_test_user=[],extra_test_pass=[],no_redfish=False,first_user=None,first_passwd=None,failed_passwd=None):
        # Check Network
        chk_err=self.error(_type='net')
        if chk_err[0]: return False,None,None
        if cancel_func is None: cancel_func=self.cancel_func
        if ip is None: ip=self.ip
        if not IpV4(ip): return False,None,None
        test_user=MoveData(self.test_user[:],self.user,to='first')
        if not test_user: test_user=['ADMIN']
        if 'ADMIN' not in test_user: test_user=['ADMIN']+test_user
        if isinstance(first_user,str) and first_user: test_user=MoveData(test_user[:],first_user,to='first')
        if extra_test_user and isinstance(extra_test_user,list):
            for i in Iterable(extra_test_user):
                if i not in test_user: test_user.append(i)
        test_passwd=self.test_passwd[:]
        if 'ADMIN' in test_passwd:
            test_passwd=MoveData(test_passwd,'ADMIN',to='first')
        else:
            test_passwd=['ADMIN']+test_passwd
        if extra_test_pass and isinstance(extra_test_pass,list):
            for i in Iterable(extra_test_pass):
                if i not in test_passwd: test_passwd.append(i)
#        test_passwd=MoveData(test_passwd,test_passwd[-1],to='first') # move last one
        if self.upasswd: test_passwd=MoveData(test_passwd,self.upasswd,to='first') # move uniq passwd
        if self.org_passwd: test_passwd=MoveData(test_passwd,self.org_passwd,to='first') # move original passwd
        if self.default_passwd and self.default_passwd not in test_passwd: test_passwd=[self.default_passwd]+test_passwd
        test_passwd=MoveData(test_passwd,self.passwd,to='first') # move current passwd
        if isinstance(first_passwd,str) and first_passwd:
            test_passwd=MoveData(test_passwd,first_passwd,to='first') # move current passwd
        for i in Iterable(self.base_passwd): # Append base password
            if i not in test_passwd: test_passwd.append(i)
        if failed_passwd:
            test_passwd=MoveData(test_passwd,failed_passwd,to='last') # move failed passwd to last
        tt=1
        #if len(self.test_passwd) > default_range: tt=2
        tt=(len(test_passwd) // default_range) + 1
        tested_user_pass=[]
        print_msg=False
        dbg_mode=0

        for mm in Iterable(self.cmd_module):
            for t in range(0,tt):
                #printf("""Try with module {} (password section:{})""".format(mm.__name__,t),log=self.log,mode='d',no_intro=True)
                if t == 0:
                    #test_pass_sample=self.test_passwd[:default_range]
                    test_pass_sample=test_passwd[:default_range]
                else:
                    #test_pass_sample=self.test_passwd[default_range:]
                    test_pass_sample=test_passwd[default_range*t:default_range*(t+1)]
                # Two times check for uniq,current,temporary password
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
# Redfish case, few times fail then blocked the account
#                                elif self.find_user_passwd_with_redfish and self.redfish: #Redfish will lock bmc user when many times failed login
#                                    rf=Redfish(host=ip,user=uu,passwd=pp)
#                                    if IsIn(rf.Power(cmd='status',silent_status_log=True),['on','off']):
#                                        chk_user_pass=True
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
                                    printf("""Check BMC USER and PASSWORD from the POOL:""",end='',log=self.log,log_level=3)
                                    print_msg=True
                                if self.log_level < 7 and not trace:
                                    printf("""p""",log=self.log,direct=True,log_level=3)
                                    printf("""({}/{})""".format(uu,pp),no_intro=False if dbg_mode > 1 else True,start_newline=True if dbg_mode > 1 else False,log=self.log,mode='d')
                                else:
                                    printf('.',log=self.log,no_intro=True)
                                    printf("""Try BMC User({}) and password({}), But failed. test next one""".format(uu,pp),no_intro=True,log=self.log,log_level=3)
                                time.sleep(1) # make to some slow check for BMC locking
                                #time.sleep(0.4)
                                dbg_mode+=1
                        else:
                            # Ping error or timeout
                            printf("""WARN: Can not ping to the destination IP({})""".format(ip),log=self.log,log_level=1,dsp='w')
                            if error:
                                self.error(_type='net',msg="Can not ping to the destination IP({})".format(ip))
                            return False,None,None
                    if self.log_level < 7 and not trace:
                        printf("""u""",log=self.log,direct=True,log_level=3)
                    #maybe reduce affect to BMC
                    time.sleep(1)
                printf("""-Tried with module {} in password section {}/{}""".format(mm.__name__,t,tt),log=self.log,mode='d',no_intro=True)
        #Whole tested but can not find
        # Reset BMC and try again
        printf(""".""",log=self.log,no_intro=True)
        printf("""no_redfish:{}""".format(no_redfish),log=self.log,dsp='d')
        if not no_redfish:
            printf("""Try McResetCold and try again, Looks BMC issue""",log=self.log)
            if self.McResetCold(no_ipmitool=True): # Block Loop
                return self.find_user_pass(ip=ip,default_range=default_range,check_cmd=check_cmd,cancel_func=cancel_func,error=error,trace=trace,no_redfish=True)
        printf("""WARN: Can not find working BMC User or password from Password POOL""",log=self.log,log_level=1,dsp='w')
        printf(""" - Password POOL  : {}""".format(test_passwd),log=self.log,dsp='d',no_intro=True)
        printf(""" - Tested Password: {}""".format(tested_user_pass),log=self.log,dsp='d',no_intro=True)
        if error:
            self.error(_type='user_pass',msg="Can not find working BMC User or password from POOL\n{}".format(tested_user_pass))
        return False,None,None

    def McResetCold(self,keep_on=20,no_ipmitool=False,**opts):
        printf("""Call Redfish""",log=self.log,log_level=1,dsp='d')
        rf=self.CallRedfish(no_ipmitool=no_ipmitool)
        if rf:
            printf("""Mc Reset Cold with Redfish""",log=self.log,log_level=1,dsp='d')
            return rf.McResetCold(keep_on=keep_on)
        if not no_ipmitool:
            if self.error(_type='net')[0]: return False # if error then error
            printf("""Mc Reset Cold with ipmitool""",log=self.log,log_level=1,dsp='d')
            return self.reset(cancel_func=self.cancel_func,post_keep_up=keep_on)
        printf("""E: Can not Reset BMC""",log=self.log,log_level=1,dsp='d')
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
            if self.error(_type='net')[0]: 
                return False,'Network issue',None
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

        if krc(rc,chk='error'):
            printf("""BMC Password: Recover fail""",log=self.log,log_level=1)
            self.warn(_type='ipmi_user',msg="BMC Password: Recover fail")
            return 'error',user,passwd
        if krc(rc,chk=True):
            printf("""Recovered BMC: from User({}) and Password({}) to User({}) and Input Password({})""".format(user,passwd,self.org_user,self.org_passwd),log=self.log,log_level=4)
            ok2,user2,passwd2=self.find_user_pass()
            if ok2:
                printf("""Confirmed changed user password to {}:{}""".format(user2,passwd2),log=self.log,log_level=4)
            else:
                return False,"Looks changed command was ok. but can not found acceptable user or password"
            self.user='{}'.format(user2)
            self.passwd='{}'.format(passwd2)
            return True,self.user,self.passwd
        else:
            if self.default_passwd:
                printf("""Not support {}. Try again with default password({})""".format(self.org_passwd,self.default_passwd),log=self.log,log_level=4)
                if self.user == self.org_user:
                    #SMCIPMITool.jar IP ID PASS user setpwd 2 <New Pass>
                    recover_cmd=mm.cmd_str("""user setpwd 2 {}""".format(FixApostrophe(self.default_passwd)))
                else:
                    #SMCIPMITool.jar IP ID PASS user add 2 <New User> <New Pass> 4
                    recover_cmd=mm.cmd_str("""user add 2 {} {} 4""".format(self.org_user,FixApostrophe(self.default_passwd)))
                printf("""Recover command: {}""".format(recover_cmd),log_level=7)
                rrc=self.run_cmd(recover_cmd)
                if krc(rrc,chk=True):
                    printf("""Recovered BMC: from User({}) and Password({}) to User({}) and Default Password({})""".format(self.user,self.passwd,self.org_user,self.default_passwd),log=self.log,log_level=4)
                    ok2,user2,passwd2=self.find_user_pass()
                    if ok2:
                        printf("""Confirmed changed user password to {}:{}""".format(user2,passwd2),log=self.log,log_level=4)
                        self.user='''{}'''.format(user2)
                        self.passwd='''{}'''.format(passwd2)
                        return True,self.user,self.passwd
            printf("""Not support original/default password. Looks need more length. So Try again with ADMIN1234""",log=self.log,log_level=4)
            if self.user == self.org_user:
                #SMCIPMITool.jar IP ID PASS user setpwd 2 <New Pass>
                recover_cmd=mm.cmd_str("""user setpwd 2 ADMIN1234""")
            else:
                #SMCIPMITool.jar IP ID PASS user add 2 <New User> <New Pass> 4
                recover_cmd=mm.cmd_str("""user add 2 {} ADMIN1234 4""".format(self.org_user))
            printf("""Recover command: {}""".format(recover_cmd),mode='d')
            rrc=self.run_cmd(recover_cmd)
            if krc(rrc,chk=True):
                printf("""Recovered BMC: from User({}) and Password(original/default) to User({}) and Password(ADMIN1234)""".format(self.user,self.org_user),log=self.log,log_level=4)
                ok2,user2,passwd2=self.find_user_pass()
                if ok2:
                    printf("""Confirmed changed user password to {}:{}""".format(user2,passwd2),log=self.log,log_level=4)
                    self.user='''{}'''.format(user2)
                    self.passwd='''{}'''.format(passwd2)
                    return True,self.user,self.passwd
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
        timeout=Int(timeout,0)
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
                         cmd_str_a=Split(cmd_str)
                         if cmd_str_a and cmd_str_a[0][0] == '/':
                             cmd_str_a[0]=os.path.basename(cmd_str_a[0])
                             cmd_str=' '.join(cmd_str_a)
                    printf('''** Do CMD   : %s
 - Path         : %s
 - Timeout      : %-15s  - Progress : %s
 - Check_RC     : %s'''%(cmd_str,path,timeout,progress,return_code),log=self.log,log_level=1,dsp='s' if show_str or not dbg else 'd')
                if self.cancel(cancel_func=cancel_func):
                    printf(' !! Canceling Job',start_newline=True,log=self.log,log_level=1,dsp='d')
                    self.warn(_type='cancel',msg="Canceling")
                    return False,(-1,'canceling','canceling',0,0,cmd_str,path),'canceling'
                #BMC Remote shell need network
                chk_err=self.error(_type='net')
                if chk_err[0]:
                    return False,(-1,'error:{}'.format(chk_err[1]),'error:{}'.format(chk_err[1]),0,0,cmd_str,path),'error'
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

                rc_0=Int(Get(rc,0))
                printf(' - RT_CODE : {}\n - Spend   : {}\n - Output  : {}'.format(rc_0,Human_Unit(Int(Get(rc,4),0)-Int(Get(rc,3),0),unit='S'),Get(rc,1)),log=self.log,log_level=1, mode='s' if show_str else 'i' if Get(rc,0) == 0 else 'd',no_intro=None)

                if 'Function access denied' in Get(rc,1):
                    return False,rc,'Locked BMC'
                elif rc_0 == 1:
                    return False,rc,'Command file not found'
                elif rc_0 == 0 or IsIn(rc_0,rc_ok):
                    return True,rc,'ok'
                elif IsIn(rc_0,rc_err_bmc_redfish): # retry after reset the BMC
                    if not self.McResetCold():
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
                    ok,ipmi_user,ipmi_pass=self.find_user_pass(failed_passwd=cur_pass)
                    if not ok:
                        self.error(_type='user_pass',msg="Can not find working IPMI USER and PASSWORD")
                        return False,'Can not find working IPMI USER and PASSWORD','user error'
                    printf('Check IPMI User and Password by {}: Found ({}/{})'.format(rc_err_bmc_user,ipmi_user,ipmi_pass),log=self.log,log_level=1,dsp='d')
                    if cur_user == ipmi_user and cur_pass == ipmi_pass:
                        printf('Looks Stuck at BMC, So reset the BMC and try again',start_newline=True,log=self.log,log_level=1,dsp='d')
                        if not self.McResetCold():
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
                            self.error(_type='user_pass',msg="Can not find working IPMI USER and PASSWORD")
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
                            else:
                                #fieltered all of issue, So return done
                                return False,rc,'unknown issue'
                        except:
                            return 'unknown',rc,'Unknown result'
        if rc is None:
            return False,(-1,'No more test','',0,0,cmd_str,path),'Out of testing'
        else:
            return False,rc,'Out of testing'

    def reset(self,retry=0,post_keep_up=20,pre_keep_up=0,retry_interval=5,cancel_func=None,timeout=1800):
        # Check Network
        chk_err=self.error(_type='net')
        if chk_err[0]: return False,chk_err[1]
        for i in range(0,1+retry):
            rc=None
            for mm in Iterable(self.cmd_module):
                ping_rc=ping(self.ip,timeout=timeout,keep_good=pre_keep_up,log=self.log,stop_func=self.error(_type='break')[0],cancel_func=cancel_func)
                if ping_rc is 0:
                    return 0,'Canceled'
                elif ping_rc is False:
                    printf('R',log=self.log,log_level=1,direct=True)
                else:
                    rc=self.run_cmd(mm.cmd_str('ipmi reset'))
                    if krc(rc,chk='error'):
                        continue # try with next module
                    elif krc(rc,chk=True):
                        time.sleep(5)
                        ping_rc=ping(self.ip,timeout=timeout,keep_good=post_keep_up,log=self.log,stop_func=self.error(_type='break')[0],cancel_func=cancel_func)
                        if ping_rc is 0:
                            return 0,'Canceled'
                        elif ping_rc is True:
                            return True,'Pinging to BMC after reset BMC'
                        else:
                            return False,'Can not Pinging to BMC after reset BMC'
                time.sleep(retry_interval)
            if krc(rc,chk='error'): #one time tested with whole modules then return error
                return rc
        return False,'Can not Pinging to BMC. I am not reset the BMC. please check the network first!'

    def get_mac(self,ip=None,user=None,passwd=None):
        if self.mac:
            return True,self.mac
        if not IpV4(ip): ip=self.ip
        if not user: user=self.user
        if not passwd: passwd=self.passwd
        # Check Network
        chk_err=self.error(_type='net')
        if chk_err[0]: return False,None
        if not self.checked_ip:
            if IpV4(ip,port=self.port):
                self.checked_ip=True
                self.checked_port=True
        for mm in Iterable(self.cmd_module):
            for i in range(0,2):
                ping_rc=ping(ip,keep_good=0,timeout=self.timeout,log=self.log,cancel_func=self.cancel_func)
                if ping_rc is False: return False,None
                
                name=mm.__name__
                cmd_str=mm.cmd_str('ipmi lan mac',passwd=passwd)
                full_str=cmd_str[1]['base'].format(ip=ip,user=user,passwd=passwd)+' '+cmd_str[1]['cmd']
                rc=rshell(full_str,log=self.log)
                if krc(rc[0],chk=True):
                    if name == 'smc':
                        mac=MacV4(rc[1])
                        if mac:
                            self.mac=mac
                            return True,self.mac
                    elif name == 'ipmitool':
                        for ii in Split(rc[1],'\n'):
                            ii_a=Split(ii)
                            if IsIn('MAC',ii_a,idx=0) and IsIn('Address',ii_a,idx=1) and IsIn(':',ii_a,idx=2):
                                mac=MacV4(ii_a[-1])
                                if mac:
                                    self.mac=mac
                                    return True,self.mac
                else:
                    if (name == 'smc' and rc[0] == 146) or (name=='ipmitool' and rc[0] == 1):
                        #If password fail or something wrong then try again after checkup password
                        ok,user,passwd=self.find_user_pass()
                        if not ok:
                            break
        return False,None

    def dhcp(self):
        for mm in Iterable(self.cmd_module):
            # Check Network
            chk_err=self.error(_type='net')
            if chk_err[0]: return False,None

            name=mm.__name__
            rc=self.run_cmd(mm.cmd_str('ipmi lan dhcp',passwd=self.passwd))
            if krc(rc,chk='error'):
                return rc
            if krc(rc,chk=True):
                if name == 'smc':
                    return True,rc[1]
                elif name == 'ipmitool':
                    for ii in Split(rc[1][1],'\n'):
                        ii_a=Split(ii)
                        if IsIn('IP',ii_a,idx=0) and IsIn('Address',ii_a,idx=1) and IsIn('Source',ii_a,idx=2):
                            return True,ii_a[-2]
        return False,None

    def gateway(self):
        for mm in Iterable(self.cmd_module):
            # Check Network
            chk_err=self.error(_type='net')
            if chk_err[0]: return False,None

            name=mm.__name__
            rc=self.run_cmd(mm.cmd_str('ipmi lan gateway',passwd=self.passwd))
            if krc(rc,chk='error'):
                return rc
            if krc(rc,chk=True):
                if name == 'smc':
                    return True,rc[1]
                elif name == 'ipmitool':
                    for ii in Split(rc[1][1],'\n'):
                        ii_a=Split(ii)
                        if IsIn('Default',ii_a,idx=0) and IsIn('Gateway',ii_a,idx=1) and IsIn('IP',ii_a,idx=2):
                            return True,ii_a[-1]
        return False,None

    def netmask(self):
        for mm in Iterable(self.cmd_module):
            # Check Network
            chk_err=self.error(_type='net')
            if chk_err[0]: return False,None
            name=mm.__name__
            rc=self.run_cmd(mm.cmd_str('ipmi lan netmask',passwd=self.passwd))
            if krc(rc,chk='error'):
                return rc
            if krc(rc,chk=True):
                if name == 'smc':
                    return True,rc[1]
                elif name == 'ipmitool':
                    for ii in Split(rc[1][1],'\n'):
                        ii_a=Split(ii)
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
        # Check Network
        chk_err=self.error(_type='net')
        if chk_err[0]: return False,chk_err[1],chk_err[1]

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
        #if self.power('off',verify=True):
        #    if self.is_down(timeout=1200,interval=5,sensor_off_monitor=5,keep_off=5)[0]:

        br_rc=self.bootorder(mode='pxe',ipxe=ipxe,force=True,persistent=persistent,set_bios_uefi=set_bios_uefi)
        if br_rc[0]:
            if self.power('on'):
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


        #    else:
        #        printf('The server still UP over 20min',log=self.log,log_level=6)
        #        return False,'The server still UP over 20min',False
        #else:
        #    printf('Can not power off the server',log=self.log,log_level=6)
        #    return False,'Can not power off the server',False

    def bootorder(self,mode=None,ipxe=False,persistent=False,force=False,boot_mode={'smc':['pxe','bios','hdd','cd','usb'],'ipmitool':['pxe','ipxe','bios','hdd']},bios_cfg=None,set_bios_uefi=True,pxe_boot_mac=None):
        rc=False,"Unknown boot mode({})".format(mode)
        ipmi_ip=self.ip
        if not MacV4(pxe_boot_mac):
            pxe_boot_mac=self.eth_mac

        def ipmitool_bootorder_setup(mm,mode,persistent,ipxe,pxe_boot_mac):
            #######################
            # Setup Boot order
            #######################
            rf=self.CallRedfish()
            if self.redfish and rf:
                # Update new information
                #ok,rf_boot=rf.Boot(boot='ipxe' if (ipxe and mode == 'pxe') or (mode == 'ipxe') else mode,mode='UEFI' if mode == 'ipxe' or (mode == 'pxe' and ipxe is True) else 'auto',keep='keep' if persistent else 'Once',force=force,set_bios_uefi=set_bios_uefi)
                #printf("[RF] {2} Boot mode set to {0} at {1}".format('ipxe' if (ipxe and mode == 'pxe') or (mode == 'ipxe') else mode,ipmi_ip,'Persistently' if persistent else 'Temporarily'),log=self.log,log_level=7)
                #rc=ok,(ok,'Persistently set to {}'.format('ipxe' if (ipxe and mode == 'pxe') or (mode == 'ipxe') else mode) if ok else rf_boot)
                rfp=rf.Power(cmd='on',sensor_up=10,sensor=True)
                if rfp is True:
                    if (ipxe is True and mode == 'pxe') or (IsIn(mode,['ipxe','uefi'])):
                        boot='pxe'
                        mode='UEFI'
                    printf("[RF] Boot: boot:{}, mode:{}, keep:{}, force:{}".format(boot,mode,True if persistent else False,force),log=self.log,mode='d')
                    ok,rf_boot=rf.Boot(boot=boot,mode=mode,keep='keep' if persistent else 'Once',force=force,set_bios_uefi=set_bios_uefi,pxe_boot_mac=pxe_boot_mac)
                    printf("[RF] SET : {}".format(ok),log=self.log,mode='d')
                    rc=ok,(ok,'{} set {} to {}'.format('Persistently' if persistent else 'Temporarily',boot,mode) if ok else rf_boot)
                    if krc(rc,chk=True):
                        return True,rc[1][1]
                    return rc
                elif rfp is None:
                    printf('Can not power on the server',log=self.log,log_level=6)
                    return False,'Can not power on the server'
                #Error then next

            # Check Network
            chk_err=self.error(_type='net')
            if chk_err[0]: return False,chk_err[1]
            if self.power('off',verify=True):
                if self.is_down(timeout=1200,interval=5,sensor_off_monitor=5,keep_off=5)[0]:

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
                    if krc(rc,chk=True):
                        return True,rc[1][1]
                    return rc
                else:
                    printf('The server still UP over 20min',log=self.log,log_level=6)
                    return False,'The server still UP over 20min'
            else:
                printf('Can not power off the server',log=self.log,log_level=6)
                return False,'Can not power off the server'

        def smcipmitool_bootorder_setup(mm,mode,persistent,ipxe):
            # Check Network
            chk_err=self.error(_type='net')
            if chk_err[0]: return False,chk_err[1]

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
            if krc(rc,chk=True):
                return True,rc[1][1]
            return rc

        def ipmitool_bootorder_status(mm,mode,bios_cfg):
            # Check Network
            chk_err=self.error(_type='net')
            if chk_err[0]: return False,None,False

            #IPMITOOL command
            if IsIn(mode,['order',None]): # Show Boot Order
                #If exist redfish then try redfish first
                rf=self.CallRedfish()
                if rf:
                    # return <RC>,<boot order information>,persistant
                    rc=rf.Boot(boot='order')
                    return rc[0],rc[1],None
                rc=self.run_cmd(mm.cmd_str('chassis bootparam get 5',passwd=self.passwd))
                # Boot Flags :
                #   - Boot Flag Invalid
                #   - Options apply to only next boot
                #   - BIOS EFI boot 
                #   - Boot Device Selector : Force PXE
                #   - Console Redirection control : System Default
                #   - BIOS verbosity : Console redirection occurs per BIOS configuration setting (default)
                #   - BIOS Mux Control Override : BIOS uses recommended setting of the mux at the end of POST
                # return <RC>,<boot order information>,persistant
                rc_str=Get(Get(rc,1),1)
#                if rc[0]:
#                    found=FIND(rc_str).Find('- Boot Device Selector : (\w.*)')
#                    if found:
#                        found=found[0] if isinstance(found,list) else found
#                        return True,found,True if 'Force' in found else False
                return rc[0],rc_str,None
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
                            if 'UEFI PXE' in Get(rf_boot_info.get('bios',{}).get('order',[]),0,default={}).get('name'):
                                status='pxe'
                                efi=True
                                persistent=True
                            elif 'Network:IBA' in Get(rf_boot_info.get('bios',{}).get('order',[]),0,default={}).get('name'):
                                status='pxe'
                                efi=False
                                persistent=True
                        else:
                            efi=True if rf_boot_info.get('bios',{}).get('mode','') == 'UEFI' else False
                            if 'Network:' in Get(rf_boot_info.get('bios',{}).get('order',[]),0,default={}).get('name'):
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
                        for ii in Split(Get(rc[1],1),'\n'):
                            if 'Options apply to all future boots' in ii:
                                persistent=True
                            elif 'BIOS EFI boot' in ii:
                                efi=True
                            elif 'Boot Device Selector :' in ii:
                                status=Split(ii,':')[1]
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
                    if krc(rc,chk=True):
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

        for mm in Iterable(self.cmd_module):
            name=mm.__name__
            chk_boot_mode=boot_mode.get(name,{})
            if name == 'smc' and mode in chk_boot_mode:
                # Setup Boot order by SMCIPMITool
                return smcipmitool_bootorder_setup(mm,mode,persistent,ipxe)

            elif name == 'ipmitool':
                # return Status
                if IsIn(mode,[None,'order','status','detail','state']):
                    return ipmitool_bootorder_status(mm,mode,bios_cfg)
                # If unknown mode then error
                elif mode not in chk_boot_mode:
                    self.warn(_type='boot',msg="Unknown boot mode({}) at {}".format(mode,name))
                    return False,'Unknown boot mode({}) at {}'.format(mode,name)
                else:
                    # Setup Boot order
                    return ipmitool_bootorder_setup(mm,mode,persistent,ipxe,pxe_boot_mac)
            else:
                return False,'Unknown module name'
        return False,rc[-1]

    def get_eth_mac(self,port=None):
        if self.eth_mac:
            return True,self.eth_mac
        rc=False,[]
        for mm in Iterable(self.cmd_module):
            name=mm.__name__
            if name == 'ipmitool':
                aaa=mm.cmd_str('''raw 0x30 0x21''',passwd=self.passwd)
                rc=self.run_cmd(aaa)
                if krc(rc,chk=True) and rc[1][1]:
                    mac_src_a=Split(rc[1][1],'\n')
                    if mac_src_a:
                        mac_source=Strip(mac_src_a[0])
                        if mac_source:
                            if len(mac_source.split()) == 10:  
                                eth_mac=MacV4(':'.join(mac_source.split()[-6:]))
                            elif len(mac_source.split()) == 16:
                                eth_mac=MacV4(':'.join(mac_source.split()[-12:-6]))
                            else:
                                eth_mac=None
                            if not eth_mac or eth_mac == '00:00:00:00:00:00':
                                rf=self.CallRedfish()
                                mac=rf.PXEMAC()
                                if MacV4(mac) and mac!= '00:00:00:00:00:00':
                                    eth_mac=mac
                            if eth_mac and eth_mac != '00:00:00:00:00:00':
                                self.eth_mac=eth_mac
                                return True,self.eth_mac
            elif name == 'smc':
                rc=self.run_cmd(mm.cmd_str('ipmi oem summary | grep "System LAN"',passwd=self.passwd))
                if krc(rc,chk=True):
                    #rrc=[]
                    #for ii in rc[1].split('\n'):
                    #    rrc.append(ii.split()[-1].lower())
                    #self.eth_mac=rrc
                    mac_src_a=Split(rc[1][1],'\n')
                    if mac_src_a:
                        eth_mac=MacV4(mac_src_a[0])
                        if eth_mac and eth_mac != '00:00:00:00:00:00':
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


    def is_up(self,timeout=1200,interval=8,sensor_on_monitor=600,reset_after_unknown=0,full_state=True,status_log=True,**opts):
        keep_on=Pop(opts,'keep_up',Pop(opts,'keep_on',30))
        keep_off=Pop(opts,'keep_down',Pop(opts,'keep_off',0))
        opts['mode']=opts.get('mode','s')
        rf=self.CallRedfish()
        if self.redfish and rf:
            rfp=rf.IsUp(timeout=Int(timeout,default=1200),keep_up=Int(keep_on,30),sensor=True if opts.get('mode','s') == 's' else False)
            if rfp is True:
                return True,'Node is UP' 
            elif rfp is None:
                return False,'Node is DOWN'
            #Error then try next
 
        rt=self.power_monitor(Int(timeout,default=1200),monitor_status=['on'],keep_off=keep_off,keep_on=keep_on,sensor_on_monitor=sensor_on_monitor,sensor_off_monitor=0,monitor_interval=interval,start=True,background=False,status_log=status_log,reset_after_unknown=reset_after_unknown,**opts)
        out=next(iter(rt.get('done').values())) if isinstance(rt.get('done'),dict) else rt.get('done')
        out_a=Split(out,'-')
        if out_a:
            lout=out_a[-1]
            if not full_state: out=lout
            if lout == 'on':
                if rt.get('repeat',0) > 0:
                    return True,'{} but repeated down and up to {}'.format(out,rt.get('repeat',0))
                return True,out
        return False,out

    def is_down_up(self,timeout=1200,sensor_on_monitor=600,sensor_off_monitor=0,interval=8,status_log=True,reset_after_unknown=0,**opts): # Node state
        keep_on=Pop(opts,'keep_up',Pop(opts,'keep_on',60))
        keep_off=Pop(opts,'keep_down',Pop(opts,'keep_off',0))
        opts['mode']=opts.get('mode','s')
        rt=self.power_monitor(Int(timeout,default=1200),monitor_status=['off','on'],keep_off=keep_off,keep_on=keep_on,sensor_on_monitor=sensor_on_monitor,sensor_off_monitor=sensor_off_monitor,monitor_interval=interval,start=True,background=False,status_log=status_log,reset_after_unknown=reset_after_unknown,**opts)
        out=next(iter(rt.get('done').values())) if isinstance(rt.get('done'),dict) else rt.get('done')
        if isinstance(rt.get('monitored_order'),list):
            if out == 'on' and 'off' in rt.get('monitored_order'):
                if rt.get('repeat',0) > 0:
                    return True,'{} but repeated down and up to {}'.format(out,rt.get('repeat',0))
                return True,out
        return False,out

    def is_down(self,timeout=1200,interval=8,sensor_off_monitor=0,full_state=True,status_log=True,reset_after_unknown=0,**opts): # Node state
        keep_on=Pop(opts,'keep_up',Pop(opts,'keep_on',0))
        keep_off=Pop(opts,'keep_down',Pop(opts,'keep_off',20))
        opts['mode']=opts.get('mode','s')
        rf=self.CallRedfish()
        if self.redfish and rf:
            rfp=rf.IsDown(timeout=Int(timeout,default=1200),keep_down=Int(keep_off,20),sensor=True if opts.get('mode','s') == 's' else False)
            if rfp is True:
                return True,'Node is DOWN' 
            elif rfp is None:
                return False,'Node is UP'
            #Error then try next

        rt=self.power_monitor(Int(timeout,default=1200),monitor_status=['off'],keep_off=keep_off,keep_on=keep_on,sensor_on_monitor=0,sensor_off_monitor=sensor_off_monitor,monitor_interval=interval,start=True,background=False,status_log=status_log,reset_after_unknown=reset_after_unknown,**opts)
        out=next(iter(rt.get('done').values())) if isinstance(rt.get('done'),dict) else rt.get('done')
        out_a=Split(out,'-')
        if out_a:
            lout=out_a[-1]
            if not full_state: out=lout
            if lout == 'off':
                if rt.get('repeat',0) > 0:
                    return True,'{} but repeated up and down to {}'.format(out,rt.get('repeat',0))
                return True,out
        return False,out

    def get_boot_mode(self):
        return self.bootorder(mode='status')

    def power(self,cmd='status',retry=0,boot_mode=None,order=False,ipxe=False,log_file=None,log=None,force=False,mode=None,verify=True,post_keep_up=20,pre_keep_up=0,post_keep_down=0,timeout=1800,lanmode=None,fail_down_time=240,cancel_func=None,set_bios_uefi_mode=False,monitor_mode='a',command_gap=5,error=False,mc_reset=False):
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
        rf=self.CallRedfish()
        if cancel_func is None: cancel_func=self.cancel_func
        if cmd == 'status':
            if self.redfish and rf:
                rfp=rf.Power('status')
                if IsIn(rfp,['on','off']): return rfp
            aa=self.do_power('status',verify=verify)
            if krc(aa[0],chk='error'):
                return 'error'
            elif aa[0]:
                return aa[1]
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
                printf('Set BootOrder output: {}'.format(rc),log=self.log,mode='d')
                time.sleep(10)
        return self.do_power(cmd,retry=retry,verify=verify,timeout=timeout,post_keep_up=post_keep_up,post_keep_down=post_keep_down,lanmode=lanmode,fail_down_time=fail_down_time,mode=monitor_mode,command_gap=command_gap,error=error,mc_reset=mc_reset)

    def do_power(self,cmd,retry=0,verify=False,timeout=1200,post_keep_up=40,post_keep_down=0,pre_keep_up=0,lanmode=None,cancel_func=None,fail_down_time=300,fail_up_time=300,mode='a',command_gap=5,error=False,mc_reset=False):
        timeout=Int(timeout,default=1200)
        command_gap=Int(command_gap,default=5)
        kfdt=TIME().Int() # keep fail down time
        kfut=TIME().Int() # keep fail up time
        total_time=TIME().Int() # total time
        rf=self.CallRedfish()

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
        for mm in Iterable(self.cmd_module):
            name=mm.__name__
            if cmd not in ['status','off_on'] + list(mm.power_mode):
                printf('Unknown command({})'.format(cmd),no_intro=True,log=self.log,log_level=1)
                self.warn(_type='power',msg="Unknown command({})".format(cmd))
                return False,'Unknown command({})'.format(cmd)

            retry=int(retry)+2
            checked_lanmode=None
            if verify or cmd == 'status':
                if self.redfish and rf:
                    rfp=rf.Power('status')
                    ok=True
                    err=None
                if not IsIn(rfp,['on','off']):
                    init_rc=self.run_cmd(mm.cmd_str('ipmi power status',passwd=self.passwd))
                    rfp=init_rc[1][1]
                    ok=init_rc[0]
                    err=init_rc[-1]
                #ERROR
                if krc(ok,chk='error'):
                    printf('Power status got some error',log=self.log,log_level=3)
                    printf(' - reason : {}'.format(err),log=self.log,no_intro=True,mode='d')
                    if error:
                        self.error(_type='power',msg=err)
                    #return init_rc[0],init_rc[1] # error the nstop
                    return ok,rfp
                #Fail
                elif ok is False:
                    if err == 'canceling':
                        printf(' Canceling',no_intro=True,log=self.log,log_level=1)
                        return True,'canceling' #cancel
                    else:
                        printf('Power status got some error',slog=self.log,log_level=3)
                        printf(' - reason : {}'.format(err),slog=self.log,no_intro=True,mode='d')
                        self.warn(_type='power',msg="Power status got some error ({})".format(err))
                        time.sleep(3) 
                        continue #Trye with next command
                #True condition
                if cmd == 'status':
                    # No need new line
                    return True,rfp
                #Get Initial status
                #init_status=Get(Get(Get(init_rc,1,default=[]),1,default='').split(),-1)
                init_status=Get(rfp.split(),-1)
                if init_status == 'off' and cmd in ['reset','cycle']:
                    cmd='on'
                # Check Pre-Keep up time
                if pre_keep_up > 0:
                    chk_pre_keep_up=self.is_up(timeout=pre_keep_up+fail_down_time+300,keep_up=pre_keep_up,cancel_func=cancel_func,keep_down=fail_down_time,mode=mode)
                    if chk_pre_keep_up[0] is False:
                        return False,chk_pre_keep_up[-1] # pre-keep up condition fail
            #Everything OK then do power 
            printf('Power({}) {} at {} (limit:{} sec)'.format(name,cmd,self.ip,timeout),log=self.log,log_level=3)
            chk=0
            rr=0
            fail_down=0
            do_power_mode=mm.power_mode[cmd]
            verify_num=len(do_power_mode)-1
            while rr < verify_num+1:
                verify_status_a=Split(do_power_mode[rr],' ')
                verify_status=verify_status_a[-1]
                if verify:
                    #if chk == 0 and init_rc[0] and init_status == verify_status:
                    if chk == 0 and ok and init_status == verify_status:
                        printf('* Already power {}'.format(verify_status),no_intro=None,log=self.log,log_level=1)
                        if chk == verify_num: #Single command then return
                            return True,verify_status
                        #Check next command
                        chk+=1
                        rr+=1
                        continue
                    # BMC Lan mode Checkup before power on/cycle/reset
                    if checked_lanmode is None and self.lanmode_convert(lanmode) in [0,1,2] and verify_status in ['on','reset','cycle']:
                       lanmode_check(lanmode)

                    if verify_status in ['reset','cycle']:
                         if init_status == 'off':
                             printf('!! Node state is off. So try power ON instead {}'.format(verify_status),log=self.log,log_level=1)
                             verify_status='on'
                printf('* Turn power {}{} '.format(verify_status,'({})'.format(fail_down) if fail_down > 0 else ''),start_newline='auto',end='',log=self.log,log_level=3,scr_dbg=False)
                ok=False
                if self.redfish and rf:
                    ok=rf.Power(verify_status,keep_up=0,keep_down=0,retry=2,timeout=60)
                    err_msg=''
                    rc_msg=verify_status
                if ok is False:
                    rc=self.run_cmd(mm.cmd_str(do_power_mode[rr],passwd=self.passwd),retry=2)
                    ok=Get(rc,0)
                    err_msg=Get(Get(rc,1),2,default=Get(Get(rc,1),1))
                    rc_msg=Get(Get(rc,1),1)
                if krc(ok,chk='error'):
                    printf(' ! power {} error\n{}'.format(verify_status,err_msg),log=self.log,log_level=3)
                    if error:
                        self.error(_type='power',msg=err_msg)
                    return ok,err_msg
                if krc(ok,chk=True):
                    if verify_status in ['reset','cycle']:
                        verify_status='on'
                        if verify:
                            time.sleep(10)
                else:
                    printf(' ! power {} fail\n{}'.format(verify_status,err_msg),log=self.log,log_level=3)
                    self.warn(_type='power',msg="power {} fail".format(verify_status))
                    time.sleep(5)
                    break # try next command
                if verify:
                    if verify_status in ['on','up']:
                        cc=TIME().Int()
                        is_up=self.is_up(timeout=timeout,keep_up=post_keep_up,cancel_func=cancel_func,keep_down=60,mode=mode)
                        if is_up[0]:
                            kfdt=TIME().Int() # keep fail down time
                            if chk < verify_num:
                                # It need new line for the next command
                                printf(self.power_on_tag,no_intro=True,log=self.log,log_level=1)
                            else: # chk >= verify_num
                                printf(self.power_on_tag,no_intro=True,log=self.log,log_level=1)
                                return True,'on'
                        elif IsIn(Get(Split(is_up[1],'-'),-1),['down','off']) and not chkd:
                            high_temp=None
                            sensor_temp=self.run_cmd(mm.cmd_str('sensor',passwd=self.passwd),retry=2)
                            if sensor_temp[0]:
                                for ssi in Split(sensor_temp[1][1],'\n'):
                                    ssi_a=Strip(ssi).split('|')
                                    if len(ssi_a) > 7 and 'Temp' in  ssi_a[0]: #ssi_a: Name, Reading, Type, Lower Non-Recoverable, Low Critical, Lower Non-Critical, Upper Non-Critical, Upper Critical, Upper Non-Recoverable
                                        #I choose upper non-recoverable value
                                        cur_temp=Int(ssi_a[1],default=0)
                                        ucr=Int(ssi_a[-2],default=0) # Threshold value
                                        unr=Int(ssi_a[-1],default=0) # critical issue value
                                        if cur_temp > 0 and ncr > 0 and cur_temp > ncr:
                                            high_temp='{} is too high({}) (over threshold {})'.format(ssi_a[0],cur_temp,ucr)
                            
                            pre_msg=' - Suddenly off' if IsIn(Get(Split(is_up[1],'-'),-2),['up','on']) else ' - Keep off(never on)'
                            if high_temp:
                                msg='{} the power over 1min after power {} command.\n - {}.'.format(pre_msg,verify_status,high_temp)
                                msg_ext='(cool down over 5min)'
                                retry_sleep=300
                            else:
                                msg="{} the power over 1min".format(pre_msg)
                                retry_sleep=20
                                msg_ext=''
                            if fail_down > retry:
                                if fail_down_time > 0 and not high_temp:
                                    if  TIME().Int() - kfdt  > fail_down_time or (TIME().Int() - total_time / fail_down_time) > 1:
                                        if error:
                                            self.error(_type='power',msg='Defined keep down(off) time({}sec) over. Maybe Stuck BMC (Try reset power for BMC)'.format(fail_down_time))
                                        return False,'Defined keep down(off) time({}sec) over. Maybe Stuck BMC (Try reset power for BMC)'.format(fail_down_time)
                                else: 
                                    if error:
                                        self.error(_type='power',msg=msg)
                                    return False,'Can not make to power UP'
                            self.warn(_type='power',msg=msg)
                            printf('{}\n - try again power {} after {}sec{}.'.format(msg,verify_status,retry_sleep,msg_ext),start_newline=True,log=self.log,log_level=1)
                            if not high_temp and mc_reset:
                                if fail_down > 1 and fail_down%2==0 and fail_down < retry:
                                    printf(' - Mc Reset Cold',no_intro=True,log=self.log,log_level=1)
                                    self.McResetCold(keep_on=retry_sleep)
                            else:
                                time.sleep(retry_sleep)
                            fail_down+=1
                            continue
                    elif verify_status in ['off','down']:
                        cc=TIME().Int()
                        is_down=self.is_down(timeout=timeout,keep_down=post_keep_down,keep_on=40,cancel_func=cancel_func,mode=mode)
                        if is_down[0]:
                            kfut=TIME().Int() # keep fail up time
                            if chk == len(mm.power_mode[cmd]):
                                printf(self.power_off_tag,no_intro=True,log=self.log,log_level=1)
                                return True,'off'
                            if chk < verify_num:
                                # It need new line for the next command
                                printf(self.power_off_tag,no_intro=True,log=self.log,log_level=1)
                            else: # chk >= verify_num
                                printf(self.power_off_tag,no_intro=True,log=self.log,log_level=1)
                                return True,'off'
                        elif IsIn(Get(Split(is_down[1],'-'),-1),['up','on']) and not chkd:
                            pre_msg=' - Suddenly on' if IsIn(Get(Split(is_up[1],'-'),-2),['off','down']) else ' - Keep on(never off)'
                            if fail_down > retry:
                                if fail_up_time > 0:
                                    if  TIME().Int() - kfut  > fail_up_time or (TIME().Int() - total_time / fail_up_time) > 1:
                                        if error:
                                             self.error(_type='power',msg='Defined keep up(on) time({}sec) over. Maybe Stuck BMC (Try reset power for BMC)'.format(fail_up_time))
                                        return False,'Defined keep up(on) time({}sec) over. Maybe Stuck BMC (Try reset power for BMC)'.format(fail_up_time)
                                else:
                                    if error:
                                        self.error(_type='power',msg='{} and Can not make to power DOWN'.format(pre_msg))
                                    return False,'{} and Can not make to power DOWN'.format(pre_msg)
                            self.warn(_type='power',msg="Something weird. Looks BMC issue, {} and can't power down".format(pre_msg))
                            printf(" - Something weird. Looks BMC issue, {} and can't power down after power {} command.\n - Try again power {}".format(pre_msg,verify_status,verify_status),start_newline=True,log=self.log,log_level=1)
                            if mc_reset:
                                if fail_down > 1 and fail_down%2==0 and fail_down < retry:
                                    printf(' - Mc Reset Cold',no_intro=True,log=self.log,log_level=1)
                                    self.McResetCold(keep_on=20)
                            else:
                                time.sleep(20)
                            fail_down+=1
                            continue
                    chk+=1
                    rr+=1
                    time.sleep(command_gap)
                else:
                    if cmd == 'off_on':
                        if verify_status in ['off','down']:
                            for i in range(0,60):
                                i_rc=False
                                i_rc_msg_a=[]
                                if self.redfish and rf:
                                    rfp=rf.Power('status')
                                    if IsIn(rfp,['on','off']):
                                       i_rc=True
                                       i_rc_msg_a=rfp.split()
                                if i_rc is False:
                                    i_rc=self.run_cmd(mm.cmd_str('ipmi power status',passwd=self.passwd))
                                    i_rc_msg=Get(Get(i_rc,1),1)
                                    i_rc_msg_a=Split(i_rc_msg)
                                if krc(i_rc,chk=True) and i_rc_msg_a: 
                                    if i_rc_msg_a[-1] == 'off':
                                        printf( self.power_off_tag ,no_intro=True,log=self.log,log_level=1)
                                        chkd=True
                                        rr+=1
                                        chk+=1
                                        break
                                    printf(self.power_on_tag if i_rc_msg_a[-1] == 'on' else self.power_off_tag ,direct=True,log=self.log,log_level=1)
                                else:
                                    printf(self.power_unknown_tag,direct=True,log=self.log,log_level=1)
                                time.sleep(2)
                            continue
                    printf(self.power_on_tag if verify_status== 'on' else self.power_off_tag ,no_intro=True,log=self.log,log_level=1)
                    #return True,Get(Get(rc,1),1)
                    return True,rc_msg
            #can not verify then try with next command
            time.sleep(3)
        if chkd:
            printf(' - It looks BMC issue. (Need reset the physical power)',log=self.log,log_level=1)
            self.error(_type='power',msg="It looks BMC issue. (Need reset the physical power)")
            return False,'It looks BMC issue. (Need reset the physical power)'
        return False,'time out'

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
            if krc(rc,chk=True):
                return True,self.lanmode_convert(mode,string=True)
            return rc
        else:
            rc=self.run_cmd(mm.cmd_str("""ipmi oem lani""",passwd=self.passwd))
            if krc(rc,chk=True):
                if mode in ['info','support']:
                    return True,Get(Get(rc,1),1)
                else:
                    a=FIND(rc[1][1]).Find('Current LAN interface is \[ (\w.*) \]')
                    if len(a) == 1:
                        return True,a[0]
            return False,None

    def error(self,_type=None,msg=None,clear=False,_type_output=None):
        # _type:
        #  ip : ip address issue (format, port issue)
        #  net : network issue (can't ping, can not access, ...)
        #  user_pass : BMC user/password issue
        #  power : Power control issue
        #  break : make break to whole BMC process or not
        #  None  : Any Error then error
        # _type_output: str or value : return error value(dictionary's value)
        #              None         : return error (dictionary type)
        # clear: True: remove error condition
        if _type and (msg or clear):
            if clear:
                if _type in self.err:
                    self.err.pop(_type)
            else:
                caller_name=FunctionName(parent=2)
                caller_name='{}() : '.format(caller_name) if isinstance(caller_name,str) else ''
                msg='{}{}'.format(caller_name,msg)
                if _type in self.err:
                    self.err[_type][TIME().Int()]=msg
                else:
                    self.err[_type]={TIME().Int():msg}
        else:
            if not _type:
                if self.err: return True,self.err
                return False,'OK'
            else:
                get_msg=self.err.get(_type,None)
                if get_msg:
                    if _type_output in [str,'str','value']:
                        return True,list(get_msg.values())[-1]
                    return True,get_msg
                return False,None

    def warn(self,_type=None,msg=None):
        if _type and msg:
            caller_name=FunctionName(parent=2)
            caller_name='{}() : '.format(caller_name) if isinstance(caller_name,str) else ''
            msg='{}{}'.format(caller_name,msg)
            if _type in self.warning:
                self.warning[_type][TIME().Int()]=msg
            else:
                self.warning[_type]={TIME().Int():msg}
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
                    self.canceling[TIME().Int()]=msg
                return True
        return False

    def is_admin_user(self,**opts):
        admin_id=opts.get('admin_id',2)
        defined_user=self.__dict__.get('user')
        found=None
        for mm in Iterable(self.cmd_module):
            #name=mm.__name__
            for j in range(0,2):
                rc=self.run_cmd(mm.cmd_str("""user list"""))
                if krc(rc,chk=True):
                    for i in Split(Get(Get(rc,1),1),'\n'):
                        i_a=Strip(i).split()
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
            for ii in Split(rc[1],'\n')[1:]:
                jj=Split(ii)
                if len(jj) == 2 and jj[1] == '(Detached)':
                    if title:
                        zz=Split(jj[0],'.')
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
                for i in range(0,2):
                    cmd_str_dict=mm.cmd_str(cmd,passwd=self.passwd)
                    if cmd_str_dict[0]:
                        base_cmd=sprintf(cmd_str_dict[1]['base'],**{'ip':self.ip,'user':self.user,'passwd':self.passwd})
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
                        break
                    elif rc[0] == 1:
                        ok,ipmi_user,ipmi_pass=self.find_user_pass()
                        if not ok:
                            if os.path.isfile(screen_tmp_file): os.unlink(screen_tmp_file)
                            return False,'IPMI User or Password not found'
                        continue
                    break
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
                for ii in Split(rc[1][1],'\n'):
                    ii_a=Split(ii)
                    if not ii_a: continue
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
                    printf(' - Monitoring timeout({} sec)'.format(timeout))
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
            for i in range(0,2):
                cmd_str_dict=mm.cmd_str('sol activate',passwd=self.passwd)
                if cmd_str_dict[0]:
                    base_cmd=sprintf(cmd_str_dict[1]['base'],**{'ip':self.ip,'user':self.user,'passwd':self.passwd})
                    cmd_str='{} {}'.format(base_cmd[1],cmd_str_dict[1].get('cmd'))
                    rc=rshell(cmd_str,interactive=True)
                    if krc(rc,chk=True):
                        return True,Get(rc,1)
                    elif i < 1:
                        ok,user,passwd=self.find_user_pass()
                        if not ok:
                            return False,'IPMI User or Password not found'
                        continue
                    return False,Get(rc,1)
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
