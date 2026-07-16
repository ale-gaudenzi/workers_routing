Option Explicit

#If VBA7 Then
    Private Declare PtrSafe Sub Sleep Lib "kernel32" (ByVal dwMilliseconds As Long)
#Else
    Private Declare Sub Sleep Lib "kernel32" (ByVal dwMilliseconds As Long)
#End If

' ==============================================================================
' Worker Task Scheduler (VBA Implementation with Dynamic Routing & Sanity Checks)
' ==============================================================================

Public Sub GenerateSchedule()
    Dim wsInput As Worksheet
    Set wsInput = ActiveSheet
    
    Dim headerRow As Range
    Set headerRow = wsInput.Rows(1)
    
    Dim colUbicazione As Integer, colTempo As Integer, colCliente As Integer
    Dim cell As Range
    For Each cell In headerRow.Cells
        If cell.Value = "" Then Exit For
        If UCase(cell.Value) = "UBICAZIONE" Then colUbicazione = cell.Column
        If UCase(cell.Value) = "TEMPO" Then colTempo = cell.Column
        If UCase(cell.Value) = "CLIENTE" Then colCliente = cell.Column
    Next cell
    
    If colUbicazione = 0 Or colTempo = 0 Or colCliente = 0 Then
        MsgBox "Missing required columns. Ensure headers are: Ubicazione, Tempo, Cliente.", vbCritical
        Exit Sub
    End If
    
    Dim depot As String
    depot = InputBox("Enter Depot Location (Starting Point):", "Scheduler Config", "Brescia, Italia")
    If Trim(depot) = "" Then Exit Sub
    
    Dim startTimeStr As String
    startTimeStr = InputBox("Enter Start Time (HH:MM):", "Scheduler Config", "08:00")
    If startTimeStr = "" Then Exit Sub
    
    Dim endTimeStr As String
    endTimeStr = InputBox("Enter End Time (HH:MM):", "Scheduler Config", "18:00")
    If endTimeStr = "" Then Exit Sub
    
    Dim lunchDurStr As String
    lunchDurStr = InputBox("Enter Lunch Duration (Hours):", "Scheduler Config", "1.0")
    If lunchDurStr = "" Then Exit Sub
    
    Dim lunchDurMins As Double
    lunchDurMins = Val(Replace(lunchDurStr, ",", ".")) * 60
    
    Dim startHour As Date, endHour As Date
    On Error Resume Next
    startHour = TimeValue(startTimeStr)
    endHour = TimeValue(endTimeStr)
    On Error GoTo 0
    
    Dim addressCache As Object
    Set addressCache = CreateObject("Scripting.Dictionary")
    
    Application.StatusBar = "Geocoding Depot..."
    Dim depotCoords As Variant
    depotCoords = GeocodeLocation(depot)
    If IsEmpty(depotCoords) Then
        MsgBox "Failed to geocode depot location.", vbCritical
        Application.StatusBar = False
        Exit Sub
    End If
    
    Dim unassignedTasks As Object
    Set unassignedTasks = CreateObject("Scripting.Dictionary")
    
    Dim lastRow As Long
    lastRow = wsInput.Cells(wsInput.Rows.Count, colUbicazione).End(xlUp).Row
    
    Dim i As Long
    Dim addr As String, taskDurationMins As Double, cliente As String
    Dim coords As Variant
    Dim taskDict As Object
    
    For i = 2 To lastRow
        addr = Trim(wsInput.Cells(i, colUbicazione).Value)
        cliente = Trim(wsInput.Cells(i, colCliente).Value)
        taskDurationMins = Val(Replace(wsInput.Cells(i, colTempo).Value, ",", ".")) * 60
        
        If addr <> "" And taskDurationMins > 0 Then
            If Not addressCache.Exists(addr) Then
                Application.StatusBar = "Geocoding: " & addr & " (Row " & i & " of " & lastRow & ")"
                coords = GeocodeLocation(addr)
                If Not IsEmpty(coords) Then
                    addressCache.Add addr, coords
                End If
            End If
            
            If addressCache.Exists(addr) Then
                Set taskDict = CreateObject("Scripting.Dictionary")
                taskDict.Add "cliente", cliente
                taskDict.Add "ubicazione", addr
                taskDict.Add "duration", taskDurationMins
                taskDict.Add "lat", addressCache(addr)(0)
                taskDict.Add "lon", addressCache(addr)(1)
                
                unassignedTasks.Add i, taskDict
            End If
        End If
    Next i
    
    Application.StatusBar = "Processing schedule routing..."
    
    Dim schedule As Collection
    Set schedule = New Collection
    
    Dim currentDay As Integer: currentDay = 1
    Dim baseDate As Date: baseDate = Date
    Dim currentTime As Date: currentTime = baseDate + startHour
    
    ' Limit is exactly end time + 30 minutes
    Dim endLimit As Date: endLimit = baseDate + endHour + TimeValue("00:30:00")
    Dim lunchStartLimit As Date: lunchStartLimit = baseDate + TimeValue("12:00:00")
    
    Dim currentLat As Double: currentLat = depotCoords(0)
    Dim currentLon As Double: currentLon = depotCoords(1)
    Dim lunchTaken As Boolean: lunchTaken = False
    
    ' Global travel cache dictionary
    Dim travelCache As Object
    Set travelCache = CreateObject("Scripting.Dictionary")
    
    AddScheduleRow schedule, currentDay, "DEPOT START", depot, Format(currentTime, "HH:mm"), Format(currentTime, "HH:mm"), "0m"
    
    Dim bestTaskKey As Variant
    Dim minTravelMins As Double
    Dim travelToTask As Double
    Dim travelToDepot As Double
    Dim simTime As Date, simLunch As Boolean
    
    Dim skippedTasks As Collection
    Set skippedTasks = New Collection
    
    Dim key As Variant
    Dim task As Object
    
    Do While unassignedTasks.Count > 0
        bestTaskKey = Empty
        minTravelMins = 999999
        
        For Each key In unassignedTasks.Keys
            Set task = unassignedTasks(key)
            
            ' Fetch from cache or API
            travelToTask = GetRoadTravelDuration(currentLat, currentLon, CDbl(task("lat")), CDbl(task("lon")), travelCache)
            travelToDepot = GetRoadTravelDuration(CDbl(task("lat")), CDbl(task("lon")), CDbl(depotCoords(0)), CDbl(depotCoords(1)), travelCache)
            
            simTime = currentTime
            simLunch = lunchTaken
            
            SimulateEvent simTime, travelToTask, simLunch, lunchStartLimit, lunchDurMins
            SimulateEvent simTime, task("duration"), simLunch, lunchStartLimit, lunchDurMins
            SimulateEvent simTime, travelToDepot, simLunch, lunchStartLimit, lunchDurMins
            
            If simTime <= endLimit Then
                If travelToTask < minTravelMins Then
                    minTravelMins = travelToTask
                    bestTaskKey = key
                End If
            End If
            DoEvents
        Next key
        
        If IsEmpty(bestTaskKey) Then
            Dim dayStartTime As Date
            dayStartTime = baseDate + startHour
            
            If currentTime = dayStartTime Then
                Dim maxDur As Double: maxDur = -1
                Dim longestKey As Variant
                For Each key In unassignedTasks.Keys
                    If unassignedTasks(key)("duration") > maxDur Then
                        maxDur = unassignedTasks(key)("duration")
                        longestKey = key
                    End If
                Next key
                skippedTasks.Add unassignedTasks(longestKey)("cliente")
                unassignedTasks.Remove longestKey
            Else
                If currentLat <> depotCoords(0) Or currentLon <> depotCoords(1) Then
                    travelToDepot = GetRoadTravelDuration(currentLat, currentLon, CDbl(depotCoords(0)), CDbl(depotCoords(1)), travelCache)
                    ExecuteEvent schedule, "RETURN TO DEPOT", depot, travelToDepot, currentTime, lunchTaken, lunchStartLimit, lunchDurMins, currentDay
                End If
                
                AddEmptyRow schedule
                
                currentDay = currentDay + 1
                baseDate = baseDate + 1
                currentTime = baseDate + startHour
                endLimit = baseDate + endHour + TimeValue("00:30:00")
                lunchStartLimit = baseDate + TimeValue("12:00:00")
                currentLat = depotCoords(0)
                currentLon = depotCoords(1)
                lunchTaken = False
                
                AddScheduleRow schedule, currentDay, "DEPOT START", depot, Format(currentTime, "HH:mm"), Format(currentTime, "HH:mm"), "0m"
            End If
        Else
            Set task = unassignedTasks(bestTaskKey)
            unassignedTasks.Remove bestTaskKey
            
            If currentLat <> task("lat") Or currentLon <> task("lon") Then
                travelToTask = GetRoadTravelDuration(currentLat, currentLon, CDbl(task("lat")), CDbl(task("lon")), travelCache)
                ExecuteEvent schedule, "TRAVEL", "To: " & task("ubicazione"), travelToTask, currentTime, lunchTaken, lunchStartLimit, lunchDurMins, currentDay
                currentLat = task("lat")
                currentLon = task("lon")
            End If
            
            ExecuteEvent schedule, CStr(task("cliente")), CStr(task("ubicazione")), CDbl(task("duration")), currentTime, lunchTaken, lunchStartLimit, lunchDurMins, currentDay
        End If
    Loop
    
    If currentLat <> depotCoords(0) Or currentLon <> depotCoords(1) Then
        travelToDepot = GetRoadTravelDuration(currentLat, currentLon, CDbl(depotCoords(0)), CDbl(depotCoords(1)), travelCache)
        ExecuteEvent schedule, "RETURN TO DEPOT", depot, travelToDepot, currentTime, lunchTaken, lunchStartLimit, lunchDurMins, currentDay
    End If
    
    Application.StatusBar = "Generating output sheet..."
    
    Dim wsOutput As Worksheet
    Set wsOutput = ThisWorkbook.Sheets.Add(After:=ThisWorkbook.Sheets(ThisWorkbook.Sheets.Count))
    wsOutput.Name = "Schedule_" & Format(Now, "hhmmss")
    
    Dim headers As Variant
    headers = Array("Day", "Cliente", "Ubicazione", "Start Time", "End Time", "Duration")
    wsOutput.Range("A1:F1").Value = headers
    wsOutput.Range("A1:F1").Font.Bold = True
    
    Dim rowIdx As Long: rowIdx = 2
    Dim rowData As Variant
    
    For i = 1 To schedule.Count
        rowData = schedule(i)
        wsOutput.Cells(rowIdx, 1).Value = rowData(0)
        wsOutput.Cells(rowIdx, 2).Value = rowData(1)
        wsOutput.Cells(rowIdx, 3).Value = rowData(2)
        wsOutput.Cells(rowIdx, 4).Value = rowData(3)
        wsOutput.Cells(rowIdx, 5).Value = rowData(4)
        wsOutput.Cells(rowIdx, 6).Value = rowData(5)
        rowIdx = rowIdx + 1
    Next i
    
    wsOutput.Columns("A:F").AutoFit
    Application.StatusBar = False
    
    Dim msg As String
    msg = "Schedule generated successfully on sheet: " & wsOutput.Name
    If skippedTasks.Count > 0 Then
        msg = msg & vbCrLf & vbCrLf & "WARNING: Skipped tasks due to exceeding daily limits:"
        For i = 1 To skippedTasks.Count
            msg = msg & vbCrLf & "- " & skippedTasks(i)
        Next i
        MsgBox msg, vbExclamation
    Else
        MsgBox msg, vbInformation
    End If
    
End Sub

' ==============================================================================
' Routing and API Functions
' ==============================================================================

Private Function GetRoadTravelDuration(ByVal Lat1 As Double, ByVal Lon1 As Double, ByVal Lat2 As Double, ByVal Lon2 As Double, ByRef travelCache As Object) As Double
    Dim cacheKey As String
    cacheKey = Round(Lat1, 4) & "|" & Round(Lon1, 4) & "|" & Round(Lat2, 4) & "|" & Round(Lon2, 4)
    
    If travelCache.Exists(cacheKey) Then
        GetRoadTravelDuration = travelCache(cacheKey)
        Exit Function
    End If
    
    Dim linearDist As Double
    linearDist = HaversineDistance(Lat1, Lon1, Lat2, Lon2)
    
    ' Se i punti sono a meno di 100 metri, viaggio 0
    If linearDist < 0.1 Then
        travelCache.Add cacheKey, 0
        GetRoadTravelDuration = 0
        Exit Function
    End If

    Dim http As Object
    Set http = CreateObject("MSXML2.ServerXMLHTTP.6.0")
    
    DoEvents
    Sleep 500
    
    Dim url As String
    Dim strLon1 As String, strLat1 As String, strLon2 As String, strLat2 As String
    
    strLon1 = Replace(CStr(Lon1), ",", ".")
    strLat1 = Replace(CStr(Lat1), ",", ".")
    strLon2 = Replace(CStr(Lon2), ",", ".")
    strLat2 = Replace(CStr(Lat2), ",", ".")
    
    url = "http://router.project-osrm.org/route/v1/driving/" & strLon1 & "," & strLat1 & ";" & strLon2 & "," & strLat2 & "?overview=false"
    
    On Error GoTo ErrorHandler
    http.Open "GET", url, False
    http.send
    
    Dim response As String
    response = http.responseText
    
    Dim durStart As Long, durEnd As Long
    Dim durStr As String
    Dim calcDuration As Double
    Dim impliedSpeed As Double
    
    durStart = InStr(response, """duration"":")
    If durStart > 0 Then
        durStart = durStart + 11
        durEnd = InStr(durStart, response, ",")
        If durEnd = 0 Then durEnd = InStr(durStart, response, "}")
        durStr = Mid(response, durStart, durEnd - durStart)
        
        calcDuration = Val(Replace(durStr, ",", ".")) / 60.0
        
        ' ---------------------------------------------------------
        ' SANITY CHECK CONTRO I BUG DI OSRM
        ' Se il server impazzisce e calcola una velocità media inferiore a 15 km/h,
        ' sovrascriviamo l'anomalia e usiamo la formula matematica.
        ' ---------------------------------------------------------
        If calcDuration > 0 Then
            impliedSpeed = linearDist / (calcDuration / 60.0)
            If impliedSpeed < 15 Then
                calcDuration = (linearDist / 50.0) * 60.0 * 1.5
            End If
        End If
        
        travelCache.Add cacheKey, calcDuration
        GetRoadTravelDuration = calcDuration
        Exit Function
    End If

ErrorHandler:
    ' Fallback nel caso in cui il server non risponda
    calcDuration = (linearDist / 50.0) * 60.0 * 1.5
    travelCache.Add cacheKey, calcDuration
    GetRoadTravelDuration = calcDuration
End Function

Private Function HaversineDistance(ByVal Lat1 As Double, ByVal Lon1 As Double, ByVal Lat2 As Double, ByVal Lon2 As Double) As Double
    Dim R As Double: R = 6371 
    Dim pi As Double: pi = 3.14159265358979
    
    Dim dLat As Double, dLon As Double
    dLat = (Lat2 - Lat1) * pi / 180
    dLon = (Lon2 - Lon1) * pi / 180
    
    Dim a As Double
    a = Sin(dLat / 2) * Sin(dLat / 2) + Cos(Lat1 * pi / 180) * Cos(Lat2 * pi / 180) * Sin(dLon / 2) * Sin(dLon / 2)
    
    Dim c As Double
    c = 2 * Atn(Sqr(a) / Sqr(1 - a + 0.000000000000001)) 
    
    HaversineDistance = R * c
End Function

Private Function GeocodeLocation(ByVal Address As String) As Variant
    Dim http As Object
    Set http = CreateObject("MSXML2.ServerXMLHTTP.6.0")
    
    DoEvents
    Sleep 1000 ' Nominatim strictly requires 1 second between requests
    
    Dim searchAddr As String
    searchAddr = Trim(Address)
    
    ' Evita omonimie costringendo la ricerca in Italia (se non già specificato)
    If InStr(1, UCase(searchAddr), "ITALIA") = 0 And InStr(1, UCase(searchAddr), "ITALY") = 0 Then
        searchAddr = searchAddr & ", Italia"
    End If
    
    Dim url As String
    url = "https://nominatim.openstreetmap.org/search?format=json&q=" & WorksheetFunction.EncodeURL(searchAddr)
    
    On Error GoTo ErrorHandler
    http.Open "GET", url, False
    http.setRequestHeader "User-Agent", "worker_scheduler_vba_client"
    http.send
    
    Dim response As String
    response = http.responseText
    
    If response = "[]" Or response = "" Then
        GeocodeLocation = Empty
        Exit Function
    End If
    
    Dim latStart As Long, latEnd As Long
    Dim lonStart As Long, lonEnd As Long
    Dim latStr As String, lonStr As String
    
    latStart = InStr(response, """lat"":""") + 7
    latEnd = InStr(latStart, response, """")
    latStr = Mid(response, latStart, latEnd - latStart)
    
    lonStart = InStr(response, """lon"":""") + 7
    lonEnd = InStr(lonStart, response, """")
    lonStr = Mid(response, lonStart, lonEnd - lonStart)
    
    Dim coords(1) As Double
    coords(0) = Val(latStr)
    coords(1) = Val(lonStr)
    
    GeocodeLocation = coords
    Exit Function
    
ErrorHandler:
    GeocodeLocation = Empty
End Function

' ==============================================================================
' Scheduling Simulation Logic
' ==============================================================================

Private Sub SimulateEvent(ByRef t As Date, ByVal durationMins As Double, ByRef lTaken As Boolean, ByVal lStartLimit As Date, ByVal lDurMins As Double)
    If durationMins = 0 Then Exit Sub
    
    If Not lTaken And t >= lStartLimit Then
        t = DateAdd("n", lDurMins, t)
        lTaken = True
    End If
    
    If Not lTaken And t < lStartLimit And DateAdd("n", durationMins, t) > lStartLimit Then
        t = DateAdd("n", durationMins + lDurMins, t)
        lTaken = True
    Else
        t = DateAdd("n", durationMins, t)
    End If
End Sub

Private Sub ExecuteEvent(ByVal schedule As Collection, ByVal eventName As String, ByVal location As String, ByVal durationMins As Double, ByRef currentTime As Date, ByRef lunchTaken As Boolean, ByVal lunchStartLimit As Date, ByVal lunchDurMins As Double, ByVal currentDay As Integer)
    Dim remaining As Double: remaining = durationMins
    Dim lunchEnd As Date
    Dim chunk As Double
    Dim endT As Date
    Dim label As String
    
    If remaining = 0 Then Exit Sub
    
    If Not lunchTaken And currentTime >= lunchStartLimit Then
        lunchEnd = DateAdd("n", lunchDurMins, currentTime)
        AddScheduleRow schedule, currentDay, "LUNCH BREAK", "N/A", Format(currentTime, "HH:mm"), Format(lunchEnd, "HH:mm"), FormatDuration(lunchDurMins)
        currentTime = lunchEnd
        lunchTaken = True
    End If
    
    Do While remaining > 0
        If Not lunchTaken And currentTime < lunchStartLimit And DateAdd("n", remaining, currentTime) > lunchStartLimit Then
            chunk = DateDiff("n", currentTime, lunchStartLimit)
            If chunk > 0 Then
                label = eventName & " (Part 1)"
                AddScheduleRow schedule, currentDay, label, location, Format(currentTime, "HH:mm"), Format(lunchStartLimit, "HH:mm"), FormatDuration(chunk)
                remaining = remaining - chunk
                currentTime = lunchStartLimit
            End If
            
            lunchEnd = DateAdd("n", lunchDurMins, currentTime)
            AddScheduleRow schedule, currentDay, "LUNCH BREAK", "N/A", Format(currentTime, "HH:mm"), Format(lunchEnd, "HH:mm"), FormatDuration(lunchDurMins)
            currentTime = lunchEnd
            lunchTaken = True
        Else
            If remaining < durationMins Then
                label = eventName & " (Part 2)"
            Else
                label = eventName
            End If
            
            endT = DateAdd("n", remaining, currentTime)
            AddScheduleRow schedule, currentDay, label, location, Format(currentTime, "HH:mm"), Format(endT, "HH:mm"), FormatDuration(remaining)
            currentTime = endT
            remaining = 0
        End If
    Loop
End Sub

Private Sub AddScheduleRow(ByVal schedule As Collection, ByVal d As Variant, ByVal c As String, ByVal u As String, ByVal st As String, ByVal et As String, ByVal dur As String)
    schedule.Add Array(d, c, u, st, et, dur)
End Sub

Private Sub AddEmptyRow(ByVal schedule As Collection)
    schedule.Add Array("", "", "", "", "", "")
End Sub

Private Function FormatDuration(ByVal minutes As Double) As String
    Dim totalMins As Long
    totalMins = CLng(minutes)
    
    Dim h As Long, m As Long
    h = totalMins \ 60
    m = totalMins Mod 60
    
    If h > 0 And m > 0 Then
        FormatDuration = h & "h " & m & "m"
    ElseIf h > 0 Then
        FormatDuration = h & "h"
    Else
        FormatDuration = m & "m"
    End If
End Function