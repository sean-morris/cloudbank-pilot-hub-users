import threading
import users
import otter_standalone_use


thread1 = threading.Thread(target=users.main, args=(True, None))
thread2 = threading.Thread(target=otter_standalone_use.main)


thread1.start()
thread2.start()

thread1.join()
thread2.join()

print("Done.")
