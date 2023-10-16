#!/usr/bin/env python3
# encoding: utf8

import sys

import rclpy
from rclpy.node import Node

import smach
import smach_ros

from ament_index_python.packages import get_package_share_directory


import rcprg_smach.conversation
import rcprg_smach.bring_jar
import rcprg_smach.smach_rcprg as smach_rcprg
import rcprg_smach.gh_csp
import rcprg_smach.update_pose

import rcprg_kb.places_xml as kb_p

from rcprg_smach.task_manager import PoseDescription

from pl_nouns.dictionary_client import DisctionaryServiceClient

from TaskER.dynamic_agent import DynAgent
from TaskER.TaskER import TaskER
from tasker_msgs.msg import RobotResource, ScheduleParams
from tasker_msgs.srv import SuspendConditionsRequest, SuspendConditionsResponse
from tasker_msgs.srv import CostConditionsRequest, CostConditionsResponse

import subprocess
import imp

kb_places = None
sim_mode = 'sim'
human_name = None


def get_package_path(package_name):
    try:
        package_path = get_package_share_directory(package_name)
        return package_path
    except LookupError:
        return None


def ptf_csp(ptf_id):
    print("calculating SP: ", ptf_id)
    global human_name
    flag = None

    if ptf_id[0] == "scheduleParams":
        return [flag, ScheduleParams(cost=10, completion_time=1, cost_per_sec=1, final_resource_state=RobotResource())]
    elif ptf_id[0] == "suspendCondition":
        req = SuspendConditionsRequest()
        req = ptf_id[1]
        return [flag, SuspendConditionsResponse(cost_per_sec=1, cost_to_resume=1)]
    elif ptf_id[0] == "startCondition":
        req = CostConditionsRequest()
        req = ptf_id[1]
        return [flag, CostConditionsResponse(cost_per_sec=1, cost_to_complete=1)]


class PulledOut():
    def __init__(self):
        self.value = False

    def set(self, trigger):
        self.value = trigger

    def get(self):
        return self.value


class MyTaskER(TaskER, Node):
    def __init__(self, da_state_name, da_name):
        global kb_places
        global sim_mode
        self.name = unicode(da_name)
        self.conversation_interface = None

        self.declare_parameter('kb_places_xml')
        self.declare_parameter('sim_mode')

        TaskER.__init__(self, da_state_name)
        self.sis = smach_ros.IntrospectionServer(
            unicode(str("/"+self.name+"smach_view_server")), self, unicode(self.name))
        self.sis.start()
        places_xml_filename = self.get_parameter('kb_places_xml').value
        self.sim_mode = str(self.get_parameter('sim_mode').value)
        assert self.sim_mode in ['sim', 'gazebo', 'real']
        sim_mode = self.sim_mode
        print('Reading KB for places from file "{}"'.format(places_xml_filename))
        self.kb_places = kb_p.PlacesXmlParser(places_xml_filename).getKB()
        kb_places = self.kb_places
        self.pulled_out = PulledOut()
        self.conversation_interface = rcprg_smach.conversation.ConversationMachine([
            ('ack',             'projects/incare-dialog-agent/agent/intents/ef92199b-d298-470c-8df3-1e1047dd70d1'),
            ('ack_i_took',      'ack_i_took'),
            ('ack_i_gave',      'ack_i_gave'),
            ('q_current_task',  'projects/incare-dialog-agent/agent/intents/8f45359d-ee47-4e10-a1b2-de3f3223e5b4'),
            ('q_load',          'projects/incare-dialog-agent/agent/intents/b8743ab9-08a1-49e8-a534-abb65155c507'),
            ('turn_around',     'projects/incare-dialog-agent/agent/intents/b4cb9f2e-2589-44dd-af14-a8f899c40ec0'),
        ], self.sim_mode)
        self.my_fsm = rcprg_smach.bring_jar.BringJar(
            self.sim_mode, self.conversation_interface, self.kb_places, self.pulled_out)

    def shutdownRequest(self):
        print("my-tasker -----------------------   shutdown")
        self.conversation_interface.stop()
        self.sis.stop()
        self.sis.clear()

    def cleanup_tf(self):
        rclpy.loginfo('{}: Executing state: {}'.format(
            rclpy.get_name(), self.__class__.__name__))
        print('Cleanup.execute')
        self.conversation_interface.stop()
        self.sis.stop()
        self.sis.clear()
        return 'ok'

    def get_suspension_tf(self, susp_data):
        print("My TASKER -- get_suspension_tf")
        print("My TASKER")
        print("My TASKER")
        rclpy.loginfo('{}: Executing state: {}'.format(
            rclpy.get_name(), self.__class__.__name__))
        print('GetSuspend.execute')
        print("susp data: ", susp_data.getData())
        print("susp data[0]: ", susp_data.getData()[0])
        data = susp_data.getData()
        fsm_executable = None
        rospack = rospkg.RosPack()

        # list all packages, equivalent to rospack list
        # rospack.list()
        print("GET_SUSPEND:\nPULLED_OUT: ", self.pulled_out.get())
        # if self.pulled_out.get() == True:
        ts_path = get_package_path('rcprg_smach')
        mod = imp.load_source("BringJarSuspension",
                              ts_path+"/src/rcprg_smach/suspend_bj.py")
        self.sis.stop()
        self.sis.clear()
        self.swap_state(u'ExeSuspension', mod.BringJarSuspension(
            self.sim_mode, self.conversation_interface, kb_places, self.pulled_out.get()))
        self.sis.start()
        fsm_executable = self.userdata.object_container
        return fsm_executable
        # else:
        #     for idx in range(2, len(data), 2):
        #         print data[idx]
        #         if data[idx] == 'executable':
        #             fsm_executable = data[idx+1]
        #         elif data[idx] == 'rosrun':
        #             ros_pkg = data[idx+1]
        #             ros_exec = data[idx+2]
        #             fsm_executable = "rosrun "+ros_pkg+" "+ros_exec
        # if fsm_executable == None:
        #     print "harmoniser did not specified executable for suspension behaviour, terminating task"
        #     fsm_executable = "terminate task"
        # return fsm_executable

    def exe_suspension_tf(self, fsm_es_in):
        print("My TASKER -- exe_suspension_tf")
        print("My TASKER")
        print("My TASKER")
        rclpy.loginfo('{}: Executing state: {}'.format(
            rclpy.get_name(), self.__class__.__name__))
        print('ExecSuspension.execute')
        # srv.shutdown()
        print(fsm_es_in)
        if fsm_es_in == None:
            return 'FINISHED'
        elif fsm_es_in == "terminate task":
            return 'shutdown'
        else:
            p = subprocess.Popen(fsm_es_in, shell=True,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # and you can block util the cmd execute finish
            p.wait()
        return 'FINISHED'

    def wait_tf(self):
        print("My TASKER -- wait_tf")
        print("My TASKER")
        print("My TASKER")
        pass

    def update_task_tf(self):
        print("My TASKER -- update_task_tf")
        print("My TASKER")
        print("My TASKER")
        self.sis.stop()
        self.sis.clear()

        imp.reload(rcprg_smach.bring_jar)
        print("SWAPPING")
        self.swap_state('ExecFSM', rcprg_smach.bring_jar.BringJar(
            self.sim_mode, self.conversation_interface, self.kb_places, self.pulled_out))
        self.sis.start()
        # self.my_fsm.set_initial_state(['MoveToKitchen'])
        pass

    def initialise_tf(self):
        print("My TASKER -- initialise")
        global human_name
        if len(sys.argv) < 3:
            raise Exception('Too few arguments: ' + str(sys.argv))
        object_container = None
        bring_destination = None
        end_pose = None
        for idx in range(1, len(sys.argv), 2):
            if sys.argv[idx] == 'object_container':
                object_container = sys.argv[idx+1]
            if sys.argv[idx] == 'bring_destination':
                bring_destination = sys.argv[idx+1]
            if sys.argv[idx] == 'end_pose':
                end_pose = sys.argv[idx+1]

        if object_container is None:
            raise Exception(
                'Argument "object_container" is missing in argv: ' + str(sys.argv))
        if isinstance(object_container, str):
            object_container = object_container.decode('utf-8')
        object_container = object_container.encode('utf-8').decode('utf-8')
        self.userdata.object_container = object_container

        if bring_destination is None:
            raise Exception(
                'Argument "bring_destination" is missing in argv: ' + str(sys.argv))
        if isinstance(bring_destination, str):
            bring_destination = bring_destination.decode('utf-8')
        bring_destination = bring_destination.encode('utf-8').decode('utf-8')
        self.userdata.bring_destination = bring_destination

        if end_pose is None:
            raise Exception(
                'Argument "end_pose" is missing in argv: ' + str(sys.argv))
        if isinstance(end_pose, str):
            end_pose = end_pose.decode('utf-8')
        end_pose = end_pose.encode('utf-8').decode('utf-8')
        self.userdata.end_pose = end_pose
        # if isinstance(goods_name, str):
        #     goods_name = goods_name.decode('utf-8')
        # goods_name = goods_name.encode('utf-8').decode('utf-8')

        # dictionary = DisctionaryServiceClient()
        # goods_name_m = dictionary.getCases(goods_name).getCase('mianownik')

        self.conversation_interface.start()

        self.userdata.fsm_es = ""


def main():
    da_name = None
    da_type = None
    da_id = None
    da_state_name = []
    for idx in range(1, len(sys.argv), 2):
        if sys.argv[idx] == 'da_name':
            da_name = sys.argv[idx+1]
        if sys.argv[idx] == 'da_type':
            da_type = sys.argv[idx+1]
        if sys.argv[idx] == 'da_id':
            da_id = sys.argv[idx+1]
    if da_name == None or da_type == None or da_id == None:
        print(
            "DA: one of the parameters (<da_name>, <da_type>, or <da_id>) is not specified")
        return 1

    da = DynAgent(da_name, da_id, da_type, ptf_csp, da_state_name)
    print("RUN BRING")
    da.run(MyTaskER(da_state_name, da_name))
    print("BG ENDED")
    return 0


if __name__ == '__main__':
    exit(main())
