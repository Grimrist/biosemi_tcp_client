char buffer;
long timer = 0;
long interval = 1000;
int writeSignal = LOW;
unsigned long current = 0;
void setup()
{
  pinMode(13, OUTPUT);
  Serial.begin(115200);
}

void loop()
{
  current = millis();
  if(current >= timer+interval) {
    digitalWrite(13, writeSignal);
  }
  if (Serial.available() > 0) {
    timer = millis();
    buffer = Serial.read();
    if(buffer == '1') {
      writeSignal = HIGH;
    }
    else if(buffer == '0') {
      writeSignal = LOW;
    }
  }
}
