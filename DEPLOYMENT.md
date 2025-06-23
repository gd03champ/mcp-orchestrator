# MCP Docker Orchestrator Deployment Guide

This guide covers the steps necessary to deploy the MCP Docker Orchestrator on an AWS EC2 instance, including the required IAM policies and Application Load Balancer (ALB) configuration.

## Prerequisites

- AWS account with administrative access
- Basic knowledge of AWS services (EC2, IAM, ALB)
- SSH access to your EC2 instance
- Docker installed on your EC2 instance

## EC2 Instance Requirements

### Instance Type Recommendations

- **Minimum**: t3.medium (2 vCPU, 4 GiB memory)
- **Recommended**: t3.large (2 vCPU, 8 GiB memory) or larger for production use
- **OS**: Amazon Linux 2 or Ubuntu 20.04 LTS or newer

### Required Software

- Docker Engine
- Python 3.8 or higher
- AWS CLI v2

## IAM Policy Configuration

The EC2 instance running the MCP Docker Orchestrator needs specific IAM permissions to manage ALB resources.

### Create IAM Policy

1. Navigate to the IAM console in AWS
2. Go to Policies → Create policy
3. Use the following JSON policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "elasticloadbalancing:DescribeTargetGroups",
        "elasticloadbalancing:CreateTargetGroup",
        "elasticloadbalancing:DeleteTargetGroup",
        "elasticloadbalancing:ModifyTargetGroupAttributes",
        "elasticloadbalancing:DescribeTargetGroupAttributes",
        "elasticloadbalancing:RegisterTargets",
        "elasticloadbalancing:DeregisterTargets",
        "elasticloadbalancing:DescribeTargetHealth"
      ],
      "Resource": "arn:aws:elasticloadbalancing:*:*:targetgroup/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "elasticloadbalancing:DescribeRules",
        "elasticloadbalancing:CreateRule",
        "elasticloadbalancing:DeleteRule",
        "elasticloadbalancing:ModifyRule"
      ],
      "Resource": "arn:aws:elasticloadbalancing:*:*:listener-rule/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "elasticloadbalancing:DescribeListeners"
      ],
      "Resource": "arn:aws:elasticloadbalancing:*:*:listener/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "elasticloadbalancing:DescribeLoadBalancers",
        "elasticloadbalancing:DescribeTags",
        "elasticloadbalancing:AddTags"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances",
        "ec2:DescribeVpcs",
        "ec2:DescribeSubnets"
      ],
      "Resource": "*"
    }
  ]
}
```

4. Name the policy `MCPOrchestratorPolicy` and add a description
5. Click "Create policy"

### Attach Policy to EC2 Instance

There are two ways to attach this policy to your EC2 instance:

#### Option 1: Using an IAM Role (Recommended)

1. In the IAM console, go to Roles → Create role
2. Select "AWS service" as the trusted entity and "EC2" as the service
3. Attach the `MCPOrchestratorPolicy` policy created earlier
4. Name the role `MCPOrchestratorRole` and create it
5. Attach this role to your EC2 instance:
   - Select your instance in the EC2 console
   - Actions → Security → Modify IAM role
   - Select the `MCPOrchestratorRole`
   - Save

#### Option 2: Using AWS CLI Credentials

If you can't use an IAM role:

1. Create an IAM user with the `MCPOrchestratorPolicy` attached
2. Generate access key and secret key for this user
3. Configure AWS CLI on your EC2 instance:

```bash
aws configure
# Enter the access key and secret key when prompted
# Specify your region (e.g., us-west-2)
```

## Application Load Balancer (ALB) Configuration

### Create an Application Load Balancer

1. Navigate to the EC2 console and select "Load Balancers"
2. Click "Create Load Balancer" and select "Application Load Balancer"
3. Basic configuration:
   - Name: `mcp-orchestrator-alb`
   - Scheme: Internet-facing (for public access) or Internal (for private access)
   - IP address type: IPv4
4. Network mapping:
   - VPC: Select your VPC
   - Mappings: Select at least two subnets in different Availability Zones
5. Security groups: 
   - Create a new security group or select an existing one
   - Ensure it allows HTTP (port 80) and/or HTTPS (port 443) from your desired sources
6. Listeners and routing:
   - Add a listener for HTTP (port 80) and/or HTTPS (port 443)
   - Create a default target group:
     - Target type: Instances
     - Name: `mcp-default`
     - Protocol: HTTP
     - Port: 80
     - Health check path: `/`
7. Register your EC2 instance with this default target group
8. Click "Create load balancer"

### Configure HTTPS (Recommended for Production)

1. In the EC2 console, select your ALB
2. Add or modify a listener for HTTPS (port 443)
3. Add an SSL/TLS certificate:
   - Use an existing ACM certificate or request a new one
   - Alternatively, import an external certificate

### Obtain Required ARNs

After creating your ALB, collect the following information:

1. ALB ARN: Available on the load balancer details page
2. Listener ARN: Click on the listener tab to find the ARN
3. VPC ID: Found in the load balancer details

You'll need these values for the `settings.conf` file.

## Deploy MCP Docker Orchestrator

### Testing Before Deployment

Before deploying to production, it's highly recommended to test the system to ensure all dependencies and functions work correctly:

1. Run the interactive test script to verify all components:

```bash
./run_tests.sh
```

This interactive script will:
- Ask which tests you want to run (all or specific tests)
- Ask if you want to clean up the environment after testing
- Create a temporary virtual environment
- Install required dependencies
- Run the selected tests
- Clean up after completion (if selected)

The available test types include:
- Dependency tests: Verify all required Python packages and system dependencies
- Orchestrator tests: Unit tests for the core orchestrator components
- Deployment tests: Simulate a deployment in a temporary directory

### Install on EC2 Instance

1. SSH into your EC2 instance
2. Clone the repository or upload the MCP Docker Orchestrator files
3. Make sure you have the necessary packages for creating Python virtual environments:

```bash
# For Ubuntu/Debian systems
sudo apt update
sudo apt install -y python3-venv python3-full

# For Amazon Linux 2
sudo yum install -y python3-pip
```

4. Run the tests in a safe environment:

```bash
./run_tests.sh
```

5. If all tests pass, run the setup script:

```bash
cd /path/to/mcp-orchestrator
sudo ./setup.sh
```

The setup script will:
- Create a Python virtual environment in `/opt/mcp-orchestrator/venv`
- Install all required Python packages in this virtual environment
- Configure the systemd service to use this virtual environment

### Configure the Orchestrator

1. Edit the `settings.conf` file:

```bash
sudo nano /opt/mcp-orchestrator/settings.conf
```

2. Update the AWS settings with your ARNs:

```ini
[aws]
region = us-west-2      # Replace with your AWS region
alb_arn = arn:aws:elasticloadbalancing:us-west-2:123456789012:loadbalancer/app/mcp-orchestrator-alb/1234567890abcdef        # Replace with your ALB ARN
listener_arn = arn:aws:elasticloadbalancing:us-west-2:123456789012:listener/app/mcp-orchestrator-alb/1234567890abcdef/1234567890abcdef      # Replace with your listener ARN
vpc_id = vpc-1234567890abcdef        # Replace with your VPC ID
```

3. Configure dashboard authentication:

```ini
[dashboard]
username = admin        # Choose a secure username
password = SECRET_PASSWORD_HERE       # Choose a strong password
path = /monitor
```

### Add MCP Server Configurations

Edit the `mcp.config.json` file to add your MCP servers:

```bash
sudo nano /opt/mcp-orchestrator/mcp.config.json
```

Example configuration:

```json
{
  "mcpServers": {
    "github-mcp-server": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "--interactive",
        "mcp/github-api:latest"
      ],
      "env": {},
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

### Start the Service

```bash
sudo systemctl start mcp-orchestrator
```

### Verify Deployment

1. Check service status:

```bash
sudo systemctl status mcp-orchestrator
```

2. View logs:

```bash
sudo journalctl -u mcp-orchestrator -f
```

3. Access the dashboard:

```
http://your-alb-dns-name/monitor
```

## Network Diagram

```
                    ┌─────────────────────────────────┐
                    │                                 │
  User Requests     │   Application Load Balancer     │
  ──────────────►   │   (path-based routing)          │
                    │                                 │
                    └─────────────────┬───────────────┘
                                      │
                                      ▼
                    ┌─────────────────────────────────┐
                    │                                 │
                    │   EC2 Instance                  │
                    │                                 │
                    │   ┌─────────────────────────┐   │
                    │   │                         │   │
                    │   │  MCP Docker Orchestrator│   │
                    │   │                         │   │
                    │   └───────────┬─────────────┘   │
                    │               │                 │
                    │               ▼                 │
                    │   ┌─────────────────────────┐   │
                    │   │                         │   │
                    │   │  Docker Containers      │   │
                    │   │  (MCP Servers)          │   │
                    │   │                         │   │
                    │   └─────────────────────────┘   │
                    │                                 │
                    └─────────────────────────────────┘
```

## Troubleshooting

### Installation Issues

1. If you encounter Python package installation errors:
   - Ensure you have Python 3.8+ installed: `python3 --version`
   - Check that you have virtual environment support: `apt install python3-venv python3-full` (for Debian/Ubuntu)
   - Make sure the user has write permissions to the installation directory
   - Check for error messages in the setup output

2. If the service fails to start:
   - Check the service logs: `journalctl -u mcp-orchestrator -n 100`
   - Verify the virtual environment was created: `ls -la /opt/mcp-orchestrator/venv/bin/python3`
   - Ensure all dependencies were installed: `/opt/mcp-orchestrator/venv/bin/pip list`

### ALB Integration Issues

1. Verify IAM permissions are correctly set up
2. Check that the ARNs in settings.conf are correct
3. Ensure the EC2 instance is in a subnet that's associated with the ALB
4. Verify security groups allow traffic between ALB and EC2 instance
5. Check the EC2 instance is healthy in the target group

### Container Issues

1. Ensure Docker is running: `sudo systemctl status docker`
2. Check Docker container logs: `docker logs mcp-{server-id}`
3. Verify the Docker images specified in mcp.config.json are accessible

### Dashboard Access Issues

1. Confirm the ALB listener rules are correctly set up
2. Verify the dashboard path matches the one in settings.conf
3. Check that the instance is receiving traffic from the ALB

## Security Best Practices

1. Use HTTPS for all traffic to and from the ALB
2. Restrict access to the dashboard using security groups
3. Use a strong password for dashboard access
4. Follow the principle of least privilege for IAM policies
5. Regularly update the EC2 instance and Docker images

## Scaling Considerations

- For high availability, consider running multiple instances behind the ALB
- Use Auto Scaling Groups to automatically manage instance lifecycle
- Consider using ECS or EKS for more robust container orchestration in large deployments

---

For additional help or troubleshooting, refer to the main README.md or open an issue in the repository.
