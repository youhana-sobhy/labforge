# LabForge: five-minute demo

A walkthrough for showing LabForge to a manager or a team. Start LabForge first
(`docker compose up -d --build`, or `scripts\start.ps1` on Windows) and open <http://localhost:8080>.
Launch one lab before the meeting so the images are already pulled.

## 1. The problem (30 seconds)

"Our physical labs are shared, scarce and out of date, so most changes get tested in production or not at
all. LabForge gives every engineer a private copy of the network in seconds, and it cleans itself up."

## 2. The catalog (45 seconds)

Open **Catalog**.

- Five ready topologies, from a training lab to a leaf-spine data centre.
- Four device types run today with open images: router, switch, firewall and host.
- Scroll down: the vendor images (Nexus 9000v, vJunos, FortiGate, PAN-OS ...) plug in through the same
  driver once we have the licences.

Click **Market Branch Office** to show the diagram, the use cases and its 8 built-in tests.

## 3. Launch (30 seconds)

Click **Launch this lab**, keep the name, pick **1 h**, and click **Launch lab**.

- The lab is ready in about two seconds. Point at **Ready in 2.1s** under the title.
- The ring at the top right counts down to auto-destroy. **+1 hour** extends it.

## 4. Prove it works (45 seconds)

Click **Run tests**. Eight tests go green in a few seconds: VLAN gateways, the eBGP session to the ISP,
the default route, internet access, and two flows that must be blocked (guest to staff, internet to staff).

"This is the evidence we attach to a change request."

## 5. Make a bad change and catch it (90 seconds)

Click **fw1**, then **Push change**. In the ruleset, change the guest rule so it allows any destination:

```
iifname "eth3" counter accept comment "GUEST -> anywhere (bad change)"
```

(Replace the line that has `oifname "eth2"` on it.) Click **Push to fw1**, close the dialog and click
**Run tests** again.

- **Guest VLAN is isolated from Staff VLAN** now fails, in red.
- "We caught a security hole in a lab, not in a branch."

Push the original line back (`iifname "eth3" oifname "eth2" counter accept ...`) and re-run: 8/8 again.

## 6. Break a link (45 seconds, optional)

Launch **WAN BGP Triangle**. Click the link between **r1** and **r3** and choose **Fail link**. Run the
tests: the r1 to r3 BGP session fails, but **Site A reaches Site C** still passes because traffic reroutes
through r2. Open the **site-a** console and run `traceroute -n 192.168.3.10` to show the new path.

## 7. Console and teardown (30 seconds)

Click **edge1**, then **Open console**. Type `show ip bgp summary`. It's a real routing stack with
the CLI engineers already know.

Click **Destroy**. Everything is gone in a second, and the lab stays in **Activity** and in the KPIs.

## 8. The numbers (30 seconds)

Open **Overview**: labs launched, engineers served, device-hours delivered, average time to ready and
test pass rate. These are the KPIs for the initiative.

## Closing line

"Same labs run in CI: every change to a topology or config is booted and tested automatically before
review. Next steps are vendor images and running it on our shared Kubernetes cluster."
