#!/usr/bin/env python3
# File name   : Kalman_Filter.py
# Website     : www.Adeept.com
# Author      : Adeept
# Date        : 2025/03/12
"""
一维卡尔曼滤波，用于平滑 ADC 采样（电池电压、光感等）。
只有一个状态量，用固定的 Q / R 递推增益，属于简化实现。
"""

# 突变阈值：与上一次滤波值相差超过该值时才加速跟随（ADC 原始量程 0-255）
JUMP_THRESHOLD = 60
# 突变时 新读数 / 旧值 的权重，0.382 / 0.618 为黄金分割，用来平滑过渡而不是硬跳
JUMP_NEW_WEIGHT = 0.382
JUMP_OLD_WEIGHT = 0.618


class Kalman_filter:
    """
    一维卡尔曼滤波器。

    :param Q: 过程噪声协方差，越大越信任新测量（跟随更快、抖动更大）
    :param R: 测量噪声协方差，越大输出越平滑（跟随更慢）
    """

    def __init__(self, Q, R):
        self.Q = Q
        self.R = R

        self.P_k_k1 = 1
        self.Kg = 0
        self.P_k1_k1 = 1
        self.x_k_k1 = 0
        self.ADC_OLD_Value = 0
        self.Z_k = 0
        self.kalman_adc_old = 0

    def kalman(self, ADC_Value):
        """输入一次 ADC 采样，返回滤波后的值（float）"""
        self.Z_k = ADC_Value

        # 变化幅度大时先做一步加权过渡，避免滤波把真实跳变吃掉
        if abs(self.kalman_adc_old - ADC_Value) >= JUMP_THRESHOLD:
            self.x_k1_k1 = ADC_Value * JUMP_NEW_WEIGHT + self.kalman_adc_old * JUMP_OLD_WEIGHT
        else:
            self.x_k1_k1 = self.kalman_adc_old

        self.x_k_k1 = self.x_k1_k1
        self.P_k_k1 = self.P_k1_k1 + self.Q

        self.Kg = self.P_k_k1 / (self.P_k_k1 + self.R)

        kalman_adc = self.x_k_k1 + self.Kg * (self.Z_k - self.kalman_adc_old)
        self.P_k1_k1 = (1 - self.Kg) * self.P_k_k1
        self.P_k_k1 = self.P_k1_k1

        self.kalman_adc_old = kalman_adc

        return kalman_adc
