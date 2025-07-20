# MaaDebugger的一些个人使用建议

>（该说明意在为计算机小白提供一些不成熟的建议）

*由于本人能力和精力原因，该程序尚未实现GUI化，想参与当前版本的测试需使用[MaaDebugger](https://github.com/MaaXYZ/MaaDebugger)*

0.MaaDebugger需要python环境，我个人之前使用的3.9版本似乎无法正常运行（当然您也可以尝试），我当前使用的版本是3.10

1.pip安装需要有良好的网络环境，您可能会需要科学上网

2.[MaaDebugger](https://github.com/MaaXYZ/MaaDebugger)官方提供的打开方式为

	python -m MaaDebugger
	
我在该程序的根目录附了一份批处理文件（Run Debugger.bat）方便您启动。以下是一些可供添加在末尾的选项：

	#设置为局域网内设备均可调试（适用于出现死循环急停）：
	
	--host 0.0.0.0

	#调整端口号（适用于初始端口已经被占用）：
	
	--port 您希望的端口号
	
	#如：--port 1145
	
以下是一份设置好的示例：

	
	python -m MaaDebugger --host 0.0.0.0 --port 1145