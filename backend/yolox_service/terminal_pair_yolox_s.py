"""Inference copy of the training experiment, YOLOX-S with one class."""
import os
from yolox.exp import Exp as BaseExp


class Exp(BaseExp):
    def __init__(self):
        super().__init__()
        self.depth = 0.33
        self.width = 0.50
        self.num_classes = 1
        self.exp_name = os.path.splitext(os.path.basename(__file__))[0]
        self.input_size = (1024, 1024)
        self.test_size = (1024, 1024)
