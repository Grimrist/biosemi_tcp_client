#include <M5Core2.h>
String data;

void setup()
{
  M5.begin(true, false, true, false); //Init M5Core2.
}

void loop()
{
  if (Serial.available() > 0) {
    data = Serial.readString();
    data.trim();
    M5.Lcd.println(data);
  }
}
