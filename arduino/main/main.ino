char buffer = 0;

void setup()
{
  pinMode(13, OUTPUT);
  Serial.begin(115200);
}

void loop()
{
  if (Serial.available() > 0) {
    buffer = Serial.read();
    Serial.print("I received: ");
    Serial.println(buffer, DEC);
    if(buffer == 1) {
      digitalWrite(13, HIGH);
    }
    else if(buffer == 0) {
      digitalWrite(13, LOW);
    }
  }
}
