"""
motor.py
封装直流电机控制 (DRV8833 / TB6612FNG)
使用两个 GPIO 控制方向 (IN1, IN2)。
"""

from machine import Pin, PWM
import time
import config

class DCMotor:
    """直流减速电机控制类"""
    
    def __init__(self, in1_pin=None, in2_pin=None, enable_pin=None, freq=1000):
        """初始化直流电机
        
        Args:
            in1_pin: IN1引脚，None则使用配置
            in2_pin: IN2引脚，None则使用配置
            enable_pin: EN引脚，None则不使用
            freq: PWM频率，默认1KHz
        """
        # 使用指定引脚或配置值
        self.in1_pin_num = in1_pin if in1_pin is not None else config.DC_MOTOR_IN1_PIN
        self.in2_pin_num = in2_pin if in2_pin is not None else config.DC_MOTOR_IN2_PIN
        
        # 初始化引脚
        try:
            self.in1 = PWM(Pin(self.in1_pin_num, Pin.OUT))
            self.in2 = PWM(Pin(self.in2_pin_num, Pin.OUT))
            
            # 设置PWM频率
            self.in1.freq(freq)
            self.in2.freq(freq)
            
            # 初始停止状态
            self.in1.duty(0)
            self.in2.duty(0)
            
            # 使能引脚（可选）
            if enable_pin:
                self.enable = Pin(enable_pin, Pin.OUT)
                self.enable.value(0)  # 默认禁用
            else:
                self.enable = None
                
            print(f"直流电机初始化成功: IN1={self.in1_pin_num}, IN2={self.in2_pin_num}")
        except Exception as e:
            print(f"直流电机初始化失败: {e}")
            # 创建空操作对象
            self.in1 = None
            self.in2 = None
            self.enable = None
    
    def forward(self, seconds=None, speed=100):
        """正转
        
        Args:
            seconds: 运行时间(秒)，None表示持续运行
            speed: 速度 (0-100)
        """
        if self.in1 is None or self.in2 is None:
            print("电机未初始化")
            return
            
        # 限制速度范围
        speed = min(max(speed, 0), 100)
        duty = int(speed * 1023 // 100)  # 转换为PWM范围(0-1023)
        
        # 启用使能（如果有）
        if self.enable:
            self.enable.value(1)
        
        # 设置方向和速度
        self.in1.duty(duty)
        self.in2.duty(0)
        
        print(f"电机正转: 速度={speed}%")
        
        # 如果指定了时间，则运行后停止
        if seconds:
            time.sleep(seconds)
            self.stop()
    
    def backward(self, seconds=None, speed=100):
        """反转
        
        Args:
            seconds: 运行时间(秒)，None表示持续运行
            speed: 速度 (0-100)
        """
        if self.in1 is None or self.in2 is None:
            print("电机未初始化")
            return
            
        # 限制速度范围
        speed = min(max(speed, 0), 100)
        duty = int(speed * 1023 // 100)  # 转换为PWM范围(0-1023)
        
        # 启用使能（如果有）
        if self.enable:
            self.enable.value(1)
        
        # 设置方向和速度
        self.in1.duty(0)
        self.in2.duty(duty)
        
        print(f"电机反转: 速度={speed}%")
        
        # 如果指定了时间，则运行后停止
        if seconds:
            time.sleep(seconds)
            self.stop()
    
    def stop(self):
        """停止电机"""
        if self.in1 is None or self.in2 is None:
            return
            
        # 停止PWM输出
        self.in1.duty(0)
        self.in2.duty(0)
        
        # 禁用使能（如果有）
        if self.enable:
            self.enable.value(0)
            
        print("电机停止")


class StepperMotor:
    """步进电机控制类 (A4988/DRV8825)"""
    
    def __init__(self, step_pin=None, dir_pin=None, enable_pin=None, steps_per_rev=200, microsteps=1):
        """初始化步进电机
        
        Args:
            step_pin: STEP引脚，None则使用配置
            dir_pin: DIR引脚，None则使用配置
            enable_pin: EN引脚，None则使用配置
            steps_per_rev: 电机每转步数，默认200步/圈(1.8°)
            microsteps: 细分数，默认1
        """
        # 使用指定引脚或配置值
        self.step_pin_num = step_pin if step_pin is not None else config.STEPPER_STEP_PIN
        self.dir_pin_num = dir_pin if dir_pin is not None else config.STEPPER_DIR_PIN
        self.enable_pin_num = enable_pin if enable_pin is not None else config.STEPPER_ENABLE_PIN
        
        # 步进电机参数
        self.steps_per_rev = steps_per_rev
        self.microsteps = microsteps
        self.total_steps = steps_per_rev * microsteps
        
        try:
            # 初始化引脚
            self.step_pin = Pin(self.step_pin_num, Pin.OUT)
            self.dir_pin = Pin(self.dir_pin_num, Pin.OUT)
            self.enable_pin = Pin(self.enable_pin_num, Pin.OUT)
            
            # 默认禁用电机(高电平禁用A4988/DRV8825)
            self.enable_pin.value(1)
            
            # 初始化方向
            self.dir_pin.value(0)
            
            # 初始化步进引脚为低电平
            self.step_pin.value(0)
            
            print(f"步进电机初始化成功: STEP={self.step_pin_num}, DIR={self.dir_pin_num}, EN={self.enable_pin_num}")
        except Exception as e:
            print(f"步进电机初始化失败: {e}")
            # 创建空操作对象
            self.step_pin = None
            self.dir_pin = None
            self.enable_pin = None
    
    def enable(self):
        """使能电机（通电保持力矩）"""
        if self.enable_pin:
            self.enable_pin.value(0)  # 低电平使能
            print("步进电机使能")
    
    def disable(self):
        """禁用电机（断电无力矩）"""
        if self.enable_pin:
            self.enable_pin.value(1)  # 高电平禁用
            print("步进电机禁用")
    
    def step(self, steps, speed_rpm=60):
        """执行指定步数的步进
        
        Args:
            steps: 步数，正数顺时针，负数逆时针
            speed_rpm: 速度(RPM)，默认60转/分钟
        """
        if self.step_pin is None or self.dir_pin is None:
            print("步进电机未初始化")
            return
            
        # 步数为0，无需动作
        if steps == 0:
            return
            
        # 设置方向
        if steps > 0:
            self.dir_pin.value(1)  # 顺时针
            steps_to_move = steps
        else:
            self.dir_pin.value(0)  # 逆时针
            steps_to_move = -steps
        
        # 计算每步延时(秒)
        # speed_rpm转/分 = (speed_rpm*steps_per_rev)/60 步/秒
        delay_s = 60 / (speed_rpm * self.steps_per_rev * self.microsteps)
        delay_us = int(delay_s * 1000000)
        
        # 确保延时不小于200微秒
        delay_us = max(delay_us, 200)
        
        print(f"步进电机步进: 步数={steps}, 速度={speed_rpm}RPM, 延时={delay_us}微秒")
        
        # 启用电机
        self.enable()
        
        # 执行步进
        for _ in range(steps_to_move):
            self.step_pin.value(1)
            time.sleep_us(delay_us // 2)
            self.step_pin.value(0)
            time.sleep_us(delay_us // 2)
        
        # 操作完成后禁用电机，节省功耗
        self.disable()
    
    def rotate_angle(self, angle, speed_rpm=60):
        """旋转指定角度
        
        Args:
            angle: 角度，正数顺时针，负数逆时针
            speed_rpm: 速度(RPM)，默认60转/分钟
        """
        # 计算角度对应的步数
        steps = int((angle / 360) * self.total_steps)
        self.step(steps, speed_rpm)
    
    def rotate_revolutions(self, revs, speed_rpm=60):
        """旋转指定圈数
        
        Args:
            revs: 圈数，正数顺时针，负数逆时针
            speed_rpm: 速度(RPM)，默认60转/分钟
        """
        # 计算圈数对应的步数
        steps = int(revs * self.total_steps)
        self.step(steps, speed_rpm) 