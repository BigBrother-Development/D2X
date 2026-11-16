import os, time
os.environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"
os.environ["SDL_HIDAPI_JOYSTICK"] = "0"  # force plain DInput view, not SDL's HIDAPI driver
import pygame

pygame.init(); pygame.joystick.init()
print("joysticks:", pygame.joystick.get_count())
for i in range(pygame.joystick.get_count()):
    j = pygame.joystick.Joystick(i); j.init()
    print(i, j.get_name(), "guid", j.get_guid(), "axes", j.get_numaxes(),
          "buttons", j.get_numbuttons(), "hats", j.get_numhats())

if pygame.joystick.get_count():
    j = next(pygame.joystick.Joystick(i) for i in range(pygame.joystick.get_count())
             if "c82d0000" in pygame.joystick.Joystick(i).get_guid())
    j.init()
    print("Squeeze each trigger SLOWLY, then press sticks/buttons. 45s...")
    end = time.time() + 45
    last = None
    while time.time() < end:
        pygame.event.pump()
        st = ([round(j.get_axis(a), 2) for a in range(j.get_numaxes())],
              [b for b in range(j.get_numbuttons()) if j.get_button(b)],
              [j.get_hat(h) for h in range(j.get_numhats())])
        if st != last:
            print(st, flush=True); last = st
        time.sleep(0.02)
