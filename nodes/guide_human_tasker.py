#!/usr/bin/env python3
# encoding: utf8

import sys
import math

import rclpy
from rclpy.node import Node

import smach
import smach_ros

import rcprg_smach.conversation
import rcprg_smach.guide_human
import rcprg_smach.gh_csp
import rcprg_smach.update_pose
import rcprg_smach.smach_rcprg as smach_rcprg

import rcprg_kb.places_xml as kb_p

from rcprg_smach.task_manager import PoseDescription

from pl_nouns.dictionary_client import DisctionaryServiceClient

from TaskER.TaskER import TaskER
from TaskER.dynamic_agent import DynAgent
from tasker_msgs.msg import RobotResource, ScheduleParams
from tasker_msgs.srv import SuspendConditionsRequest, SuspendConditionsResponse
from tasker_msgs.srv import CostConditionsRequest, CostConditionsResponse
# for ExeSuspension state
import subprocess
import imp
from tf.transformations import quaternion_from_euler, euler_from_quaternion
from geometry_msgs.msg import Pose
kb_places = None
sim_mode = None
human_name = None
guide_destination = None
greeted = None


def ptf_csp(ptf_id):
    print("calculating SP: ", ptf_id)
    global kb_places
    global sim_mode
    global human_name
    global guide_destination
    global greeted
    # set flag 'self-terminate' to terminate DA if in Wait or Init state
    flag = None
    csp_handler = rcprg_smach.gh_csp.GH_csp(human_name)
    is_human = False
    robot_pose_updater = rcprg_smach.update_pose.UpdatePose(
        sim_mode, kb_places, "Rico")
    robot_pose_updater.update_pose("/base_link", False, is_human)
    robot_pose = csp_handler.get_robot_pose(sim_mode, kb_places, "Rico")
    is_human = True
    human_pose_updater = rcprg_smach.update_pose.UpdatePose(
        sim_mode, kb_places, human_name)
    human_frame = "/"+human_name
    human_pose_updater.update_pose(human_frame, False, is_human)
    human_pose = csp_handler.get_robot_pose(sim_mode, kb_places, human_name)
    human_approach_pose = Pose()
    human_yaw = euler_from_quaternion(
        [human_pose.orientation.x, human_pose.orientation.y, human_pose.orientation.z, human_pose.orientation.w])[2]
    human_approach_pose.position.x = human_pose.position.x + \
        1*math.cos(human_yaw)
    human_approach_pose.position.y = human_pose.position.y + \
        1*math.sin(human_yaw)
    (human_approach_pose.orientation.x, human_approach_pose.orientation.y,
     human_approach_pose.orientation.z, human_approach_pose.orientation.w) = quaternion_from_euler(0, 0, human_yaw-math.pi)
    # print "H_approach: ", human_approach_pose

    destination_pose = csp_handler.get_robot_pose(
        sim_mode, kb_places, guide_destination)
    if destination_pose == 'is-volumetric':
        destination_pose = csp_handler.get_robot_pose(
            sim_mode, kb_places, guide_destination, human_name)
    if ptf_id[0] == "scheduleParams":
        return [flag, csp_handler.get_schedule_params_gh(robot_pose, human_approach_pose, destination_pose, human_name)]
        # return ScheduleParams(cost = 1, completion_time=1,cost_per_sec=1,final_resource_state=RobotResource())
    elif ptf_id[0] == "suspendCondition":
        req = SuspendConditionsRequest()
        req = ptf_id[1]
        return [flag, csp_handler.get_suspend_conditions_gh(req, greeted.get(), human_approach_pose)]
    elif ptf_id[0] == "startCondition":
        req = CostConditionsRequest()
        req = ptf_id[1]
        # CostConditionsResponse(cost_per_sec=1, cost_to_complete=1)]
        return [flag, csp_handler.get_cost_conditions_gh(req, human_approach_pose, human_name)]


class Greeted():
    def __init__(self):
        self.value = False

    def set(self, trigger):
        self.value = trigger

    def get(self):
        return self.value


class MyTaskER(TaskER):
    def __init__(self, da_state_name, da_name):
        self.name = unicode(da_name)
        rclpy.init_node(self.name)
        self.sim_mode = None
        self.conversation_interface = None
        global kb_places
        global sim_mode
        global human_name
        global guide_destination
        global greeted
        kb_places = None
        TaskER.__init__(self, da_state_name)
        rclpy.init_node(self.name)
        self.sis = smach_ros.IntrospectionServer(
            unicode(str("/"+self.name+"smach_view_server")), self, unicode(self.name))
        self.sis.start()
        places_xml_filename = rclpy.get_param('/kb_places_xml')
        self.sim_mode = str(rclpy.get_param('/sim_mode'))
        assert self.sim_mode in ['sim', 'gazebo', 'real']
        sim_mode = self.sim_mode
        print('Reading KB for places from file "' + places_xml_filename + '"')
        kb_places = kb_p.PlacesXmlParser(places_xml_filename).getKB()

        self.conversation_interface = rcprg_smach.conversation.ConversationMachine([
            ('ack',             'projects/incare-dialog-agent/agent/intents/ef92199b-d298-470c-8df3-1e1047dd70d1'),
            ('ack_i_took',      'ack_i_took'),
            ('ack_i_gave',      'ack_i_gave'),
            ('q_current_task',  'projects/incare-dialog-agent/agent/intents/8f45359d-ee47-4e10-a1b2-de3f3223e5b4'),
            ('q_load',          'projects/incare-dialog-agent/agent/intents/b8743ab9-08a1-49e8-a534-abb65155c507'),
            ('turn_around',     'projects/incare-dialog-agent/agent/intents/b4cb9f2e-2589-44dd-af14-a8f899c40ec0'),
        ], self.sim_mode)
        self.greeted = Greeted()
        greeted = self.greeted
        self.my_fsm = rcprg_smach.guide_human.GuideHuman(
            self.sim_mode, self.conversation_interface, kb_places, self.greeted)
        human_name = None
        guide_destination = None
        for idx in range(1, len(sys.argv), 2):
            if sys.argv[idx] == 'human_name':
                human_name = sys.argv[idx+1]
            if sys.argv[idx] == 'guide_destination':
                guide_destination = sys.argv[idx+1]
        if human_name is None:
            raise Exception(
                'Argument "human_name" is missing in argv: ' + str(sys.argv))

        if isinstance(human_name, str):
            human_name = human_name.decode('utf-8')
        human_name = human_name.encode('utf-8').decode('utf-8')
        if isinstance(guide_destination, str):
            guide_destination = guide_destination.decode('utf-8')
        guide_destination = guide_destination.encode('utf-8').decode('utf-8')

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
        global kb_places
        # fsm_executable = None
        # for idx in range(2, len(data), 2):
        #     print data[idx]
        #     if data[idx] == 'executable':
        #         fsm_executable = data[idx+1]
        #     elif data[idx] == 'rosrun':
        #         ros_pkg = data[idx+1]
        #         ros_exec = data[idx+2]
        #         fsm_executable = "rosrun "+ros_pkg+" "+ros_exec
        # if fsm_executable == None:
        #     print "harmoniser did not specified executable for suspension behaviour, terminating task"
        #     fsm_executable = "terminate task"
        # get an instance of RosPack with the default search paths
        rospack = rospkg.RosPack()

        # list all packages, equivalent to rospack list
        rospack.list()
        print("GET_SUSPEND:GREETED: ", self.greeted.get())
        if self.greeted.get() == True:
            # get the file path for rclpy_tutorials
            ts_path = rospack.get_path('rcprg_smach')
            mod = imp.load_source(
                "SuspGH", ts_path+"/src/rcprg_smach/suspend_gh.py")
            self.sis.stop()
            self.sis.clear()
            self.swap_state(u'ExeSuspension', mod.SuspGH(
                self.sim_mode, self.conversation_interface, kb_places))
            self.sis.start()
            fsm_executable = self.userdata.human_name
            return fsm_executable
        else:
            fsm_executable = None
            return fsm_executable

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
        global kb_places

        imp.reload(rcprg_smach.guide_human)
        print("SWAPPING")
        self.swap_state('ExecFSM', rcprg_smach.guide_human.GuideHuman(
            self.sim_mode, self.conversation_interface, kb_places, self.greeted))
        self.sis.start()
        # self.my_fsm.set_initial_state(['MoveToKitchen'])
        pass

    def initialise_tf(self):
        print("My TASKER -- initialise")
        if len(sys.argv) < 3:
            raise Exception('Too few arguments: ' + str(sys.argv))

        goods_name = None
        for idx in range(1, len(sys.argv), 2):
            if sys.argv[idx] == 'human_name':
                human_name = sys.argv[idx+1]
            if sys.argv[idx] == 'guide_destination':
                guide_destination = sys.argv[idx+1]

        if human_name is None:
            raise Exception(
                'Argument "human_name" is missing in argv: ' + str(sys.argv))
        if guide_destination is None:
            raise Exception(
                'Argument "guide_destination" is missing in argv: ' + str(sys.argv))

        if isinstance(human_name, str):
            human_name = human_name.decode('utf-8')
        human_name = human_name.encode('utf-8').decode('utf-8')
        if isinstance(guide_destination, str):
            guide_destination = guide_destination.decode('utf-8')
        guide_destination = guide_destination.encode('utf-8').decode('utf-8')

        self.conversation_interface.start()

        self.userdata.human_name = unicode(human_name)
        self.userdata.guide_destination = unicode(guide_destination)
        self.userdata.fsm_es = ""


def main(args=None):
    rclpy.init(args=args)

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

    if da_name is None or da_type is None or da_id is None:
        print(
            "DA: one of the parameters (<da_name>, <da_type>, or <da_id>) is not specified")
        return 1

    da = DynAgent(da_name, da_id, da_type, ptf_csp, da_state_name)
    print("RUN BRING")
    da.run(MyTaskER(da_state_name, da_name))
    print("BG ENDED")
    return 0


if __name__ == '__main__':
    main()
    print("ALLLLLLL CLOOOOOSSSSEEEEED")
